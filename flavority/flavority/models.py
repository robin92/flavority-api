
from binascii import hexlify
from datetime import datetime, timezone, date
from hashlib import sha256
import json
from re import compile as Regex
from os import urandom
import traceback

from flavority import app
from flavority.auth.mixins import UserMixin

db = app.db

#Associations aka Logic tables (many-to-many connections)
#DEL -> te takie inne niebieskie tabelki w uml'u, dla mnie to one sa niebieskie ale pewnie jakos inaczej ten kolor sie zwie, whatever
#Table will connect Ingredients with Recipes
class IngredientAssociation(db.Model):

    __tablename__ = 'IngredientAssociation'

    recipe_id = db.Column(db.Integer, db.ForeignKey('Recipe.id'), primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('Ingredient.id'), primary_key=True)
    amount = db.Column(db.Integer)

    ingredient = db.relationship('Ingredient')


tag_assignment = db.Table('tag_assignment',
                          db.Column('recipe', db.Integer, db.ForeignKey('Recipe.id')),
                          db.Column('tag', db.Integer, db.ForeignKey('Tag.id')))
favour_recipes = db.Table('favour_recipes',
                          db.Column('user', db.Integer, db.ForeignKey('User.id')),
                          db.Column('recipe', db.Integer, db.ForeignKey('Recipe.id')))
#End of associations declaration

def serialize_date(dt):

    return dt.isoformat()

def to_json_dict(inst, cls, extra_content={}):
    """
    Jsonify the sql alchemy query result.

    in extra_content you can put any stuff you want to have in your json
    e.g. sth that is not a column
    """
    convert = dict()
    convert[db.Date] = lambda dt: dt.isoformat()
    convert[db.DateTime] = lambda dt: dt.isoformat()
    # add your coversions for things like datetime's
    # and what-not that aren't serializable.
    d = dict()
    for c in cls.__table__.columns:
        v = getattr(inst, c.name)
        if type(c.type) in convert.keys() and v is not None:
            try:
                d[c.name] = convert[type(c.type)](v)

            except:
                traceback.print_exc()
                d[c.name] = "Error:  Failed to covert using ", str(convert[type(c.type)])
        elif v is None:
            d[c.name] = str()
        else:
            d[c.name] = v
    d.update(extra_content)
    #return json.dumps(d)
    return d


class User(db.Model, UserMixin):

    # should be sufficient
    EMAIL_LENGTH    = 128
    
    EMAIL_REGEX   = Regex(r'([A-Za-z._0-9]+)@([A-Za-z._0-9]{2,}.[a-z]{2,})')
    
    # maximum hash length: 512 b == to bytes => 64 B == base16 => 128 B
    # this will allow for quite nice changing between hash algorithms
    PASSWORD_LENGTH = 64 * 2
    
    # size (in bytes) of salt+password's hash
    HASH_SIZE   = 32
    
    # used by SQLAlchemy if native enums is supported by database
    USER_TYPE_ENUM_NAME = "UserType"

    # allowed user types keys
    USER_TYPE_COMMON    = "common"
    USER_TYPE_ADMIN     = "admin"
    
    # allowed user values
    USER_TYPES  = {
            USER_TYPE_COMMON: "COMMON",
            USER_TYPE_ADMIN: "ADMINISTRATOR"
        }

    TOKEN_LENGTH = 1024

    __tablename__ = "User"    
    id = db.Column(db.Integer, primary_key = True)
    email = db.Column(db.String(EMAIL_LENGTH), unique = True, nullable = False)
    salt  = db.Column(db.String(PASSWORD_LENGTH), nullable = False)
    password = db.Column(db.String(PASSWORD_LENGTH), nullable = False)
    type = db.Column(db.Enum(*tuple(USER_TYPES.values()), name = USER_TYPE_ENUM_NAME), default = USER_TYPES[USER_TYPE_COMMON])
#    token = db.Column(db.String(TOKEN_LENGTH), default=None)
    favourites = db.relationship('Recipe', secondary=favour_recipes)

    @staticmethod
    def gen_salt(length = HASH_SIZE):
        return urandom(length)
        
    @staticmethod
    def combine(salt, pwd):
        return salt + pwd

    @staticmethod
    def hash_pwd(bytes):
        return sha256(bytes).hexdigest()

    @staticmethod
    def is_valid_email(text):
        return User.EMAIL_REGEX.match(text) is not None
       
    def __init__(self, email, password, type = None):
        # validate arguments
        if not User.is_valid_email(email): raise ValueError()
        
        # set fields values
        self.email = email
        self.salt = hexlify(User.gen_salt())
        self.password = User.hash_pwd(User.combine(self.salt, password.encode()))
        if type is not None and type in User.USER_TYPES: self.type = User.USER_TYPES[type]

    def get_id(self):
        return self.id

    def __repr__(self):
        return '<User: %r, with password: %r and email: %r>' % (self.id,  self.password, self.email)
#End of 'User' class declaration


#Class represents the recipe's object with name 'Recipe'
#Arg: db.Model - model from SQLAlchemy database
class Recipe(db.Model):
    
    DESCRIPTION_LENGTH = 120
    
    __tablename__ = 'Recipe'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dish_name = db.Column(db.String(DESCRIPTION_LENGTH))
    author_id = db.Column(db.Integer, db.ForeignKey('User.id'))
    author = db.relationship('User', backref=db.backref('recipes', lazy='dynamic'))
    creation_date = db.Column(db.DateTime)
    preparation_time = db.Column(db.SmallInteger)
    photo = db.Column(db.BLOB)
    recipe_text = db.Column(db.Text)
    tasteMark = db.Column(db.Float)
    difficultyMark = db.Column(db.Float)
    rank = db.Column(db.Float)
    eventToAdminControl = db.Column(db.Boolean)
    portions = db.Column(db.SmallInteger)
    ingredients = db.relationship('IngredientAssociation', cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary=tag_assignment)
    
    def __init__(self, dish_name, creation_date, preparation_time, recipe_text, portions, author):
        self.dish_name = dish_name
        if creation_date is None:
            self.creation_date = datetime.now()
        self.preparation_time = preparation_time
        self.recipe_text = recipe_text
        self.portions = portions
        self.author = author
    
    def __repr__(self):
        return '<Recipe name : %r, posted by : %r>' % (self.dish_name, self.author_id)

    def to_json_short(self):
        return {
            "id": self.id,
            "dishname": self.dish_name,
            "creation_date": self.creation_date,
            "photo": None,
            "rank": self.rank,
            "tags": [i.json for i in self.tags],
        }

    @property
    def json(self):
        extra_content = {}
        tags = {} if self.tags is None else {'tags': [i.json for i in self.tags]}
        extra_content.update(tags)
        ingredients = {} if self.ingredients is None else \
            {'ingredients': [{"ingr_id": i.ingredient_id, "amount": i.amount} for i in self.ingredients]}
        extra_content.update(ingredients)
        return to_json_dict(self, self.__class__, extra_content)
#End of 'Recipe' class declaration


#Class represents the Comment's object with name 'Comment'
#Arg: db.Model - model from SQLAlchemy database
class Comment(db.Model):
    
    COMMENT_TITLE_LENGTH = 120
    
    __tablename__ = 'Comment'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(COMMENT_TITLE_LENGTH))
    text = db.Column(db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey('User.id'))
    author = db.relationship('User', backref=db.backref('comments', lazy='dynamic'))        #DELmany to one z comment do usera
    recipe_id = db.Column(db.Integer, db.ForeignKey('Recipe.id'))
    recipe = db.relationship('Recipe', backref=db.backref('recipes', lazy='dynamic'))       #DElmany to one z comment do recipe
    
    def __init__(self, title, text, author_id, recipe_id):
        self.title = title
        self.text = text
        self.author_id = author_id
        self.recipe_id = recipe_id
    
    def __repr__(self):
        return '<Comment: %r, with text: %r>' % (self.title, self.text)
#End of 'Comment' class declaration


#Class represents the Rate object with name 'Rate'
#Arg: db.Model - model from SQLAlchemy database
class Rate(db.Model):
    __tablename__ = 'Rate'
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('User.id'))
    author = db.relationship('User', backref=db.backref('rates', lazy='dynamic'))       #DELmany to one z rate do usera
    recipe_id = db.Column(db.Integer, db.ForeignKey('Recipe.id'))
    recipe = db.relationship('Recipe', backref=db.backref('rates', lazy='dynamic'))       #DELmany to one z comment do recipe
    taste_rate = db.Column(db.SmallInteger)
    difficulty_rate = db.Column(db.SmallInteger)
    
    def __init__(self, taste, difficulty, author, recipe):
        self.taste_rate = taste
        self.difficulty_rate = difficulty
        self.author = author
        self.recipe = recipe
    
    def __repr__(self):
        return '<Rate from userID : %r, to recipeID : %r, taste : %r, difficulty : %r>' % (self.author_id, self.recipe_id, self.taste_rate, self.difficulty_rate)
#End of 'Rate' class declaration


#Class represents the Ingredient's object with name 'Ingredient'
#Arg: db.Model - model from SQLAlchemy database
class Ingredient(db.Model):
    
    INGREDIENT_NAME_LENGTH = 100
    
    __tablename__ = 'Ingredient'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(INGREDIENT_NAME_LENGTH), unique=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('Unit.id'))
    unit = db.relationship('Unit', backref=db.backref('units', lazy='dynamic'))
    
    def __init__(self, name):
        self.name = name
    
    def __repr__(self):
        return '<Ingredient\'s name : %r>' % self.name
#End of 'Ingredient' class declaration


#Class represents the Unit's object with name 'Unit'
#Arg: db.Model - model from SQLAlchemy database
class Unit(db.Model):
    
    UNIT_NAME_LENGTH = 40
    
    __tablename__ = 'Unit'
    id = db.Column(db.Integer, primary_key=True)
    unit_name = db.Column(db.String(UNIT_NAME_LENGTH), unique=True) #DELtak mi sie wydaje :P
    unit_value = db.Column(db.Float)
    other_id = db.Column(db.Integer, db.ForeignKey('Unit.id'))      #DELnie do konca zalapalem czemu, ale to musi tu zostac
    others = db.relationship('Unit', remote_side=[id])              #DELwedle wszelkich znakow w internetach ta relacja many to one powinna chodzic
    #DELsee -> Adjacency List Relationships at SQLAlchemy
    def __init__(self, unit_name, unit_value, others):
        self.unit_name = unit_name
        self.unit_value = unit_value
        self.others = others
    
    def __repr__(self):
        return '<Unit : %r, with value : %r>' % (self.unit_name, self.unit_value)
#End of 'Unit' class declaration


#Class represents the Tag's object with name 'Tag'
#Arg: db.Model - model from SQLAlchemy database
class Tag(db.Model):
    
    TAG_NAME_LENGTH = 40
    TAG_TYPE_LENGTH = 39
    
    __tablename__ = 'Tag'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(TAG_NAME_LENGTH), unique=True)
    type = db.Column(db.String(TAG_TYPE_LENGTH))
    
    def __init__(self, name, type):
        self.name = name
        self.type = type
    
    def __repr__(self):
        return '<Tag name : %r and type : %r>' % (self.name, self.type)

    @property
    def json(self):
        return to_json_dict(self, self.__class__)
#End of 'Tag' class declaration
#EOF
