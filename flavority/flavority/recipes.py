
import traceback
from functools import reduce
from os.path import abspath, join

from flask import request
from flask.ext.restful import Resource, reqparse
from flask_restful import abort

from . import lm, app
from .models import Recipe, Tag, tag_assignment, Ingredient, IngredientAssociation, User
from .util import Flavority, ViewPager
from .photos import PhotoResource


##Class that handles method for Recipe object
class Recipes(Resource):
    ##Variable that represents items shown per page
    GET_ITEMS_PER_PAGE = 10

    ##Method that handles get request arguments
    #May return ValueError
    @staticmethod
    def parse_get_arguments():
        def cast_bool(x):
            if x.lower() == '': return True
            elif x.lower() == 'false': return False
            elif x.lower() == 'true': return True
            try:
                return bool(x)
            except ValueError:
                return False

        def cast_sort(x):
            sortables, x = ['id', 'date_added', 'rate'], x.lower()
            return x if x in sortables else sortables[0]

        def cast_natural(x):
            try: i = int(x)
            except ValueError: return 1
            return i if i >= 1 else 1

        parser = reqparse.RequestParser()
        parser.add_argument('short', type=cast_bool)
        parser.add_argument('sort_by', type=cast_sort, default='id')
        parser.add_argument('page', type=cast_natural, default=1)
        parser.add_argument('limit', type=cast_natural, default=Recipes.GET_ITEMS_PER_PAGE)
        parser.add_argument('user_id', type=int, default=None)
        parser.add_argument('query', type=str)
        parser.add_argument('tag_id', type=int, default=None, action='append')
        parser.add_argument('advanced', type=cast_bool, default=False)
        parser.add_argument('myrecipes', type=cast_bool, default=False)
        return parser.parse_args()

    ##Method that handles options for request
    def options(self):
        return None

    ##Method that handles GET request
    def get(self):
        args = self.parse_get_arguments()

        query = Recipe.query

        if args['advanced']:
#          funkcja do napisania dla Patryka
#           w query znajduje sie lista skladnikow
           return #advancedSearch(args['query'], args['page'], args['limit'])

        # only recipes containg at least one of the requested tags
        #   this piece of code may require an explanation:
        #       the idea is to take all recipes marked with a given tag (one) and union results
        #       in order to avoid None objects they're filtered out
        if args.tag_id is not None:
            query = reduce(
                lambda q1, q2: q1.union(q2),
                map(
                    lambda tag: tag.recipes,
                    filter(lambda x: x is not None, [Tag.query.get(i) for i in args.tag_id])))

        # only recipes from given user
        if args['user_id']:
            query = query.filter(Recipe.author_id == args['user_id'])
        elif args['myrecipes']:
            user = lm.get_current_user()
            query = user.recipes
        
        # search string in titles
        if args['query'] is not None:
            pattern = args['query'].lower()
            query = query.filter(Recipe.dish_name.like('%{}%'.format(pattern)))

        # select proper sorting key
        query = {
            'id': lambda x: x,
            'date_added': lambda x: x.order_by(Recipe.creation_date.desc()),
            'rate': lambda x: x.order_by(Recipe.taste_comments.desc())
        }[args['sort_by']](query)
        total_elements = query.count()
        query = ViewPager(query, page=args['page'], limit_per_page=args['limit'])

        # return short or standard form as requested
        func = lambda x: x.to_json()
        if args['short']:
            func = lambda x: x.to_json_short(get_photo=lambda photo: photo.id)

        return {
            'recipes': list(map(func, query.all())),
            'totalElements': total_elements,
        }

    ##Method that handles POST request
    @lm.auth_required
    def post(self):
        args = Recipes.get_form_parser().parse_args()

        recipe = Recipe(args.dish_name, None, args.preparation_time, args.recipe_text, args.portions, lm.get_current_user())
        Recipes.add_tags(recipe, args.tags)
        Recipes.add_ingredients(recipe, args.ingredients)

        # TODO: add rest of the arguments

        app.logger.debug(recipe)
        try:
            app.db.session.add(recipe)
            app.db.session.commit()
        except:
            traceback.print_exc()
            app.db.session.rollback()
            return Flavority.failure(), 500

        return Flavority.success(), 201

    ##Method returns object with arguments taken from parser
    @staticmethod
    def get_form_parser():
        parser = reqparse.RequestParser()
        parser.add_argument('dish_name', type=str, required=True, help="dish name")
        parser.add_argument('recipe_text', type=str, required=True, help="recipe text")
        parser.add_argument('preparation_time', type=int, required=True, help="preparation time")
        parser.add_argument('portions', type=int, required=True, help="portions")
        parser.add_argument('tags', type=list, required=False, help="tags", action="append")
        parser.add_argument('ingredients', type=list, required=True, help="ingredients")

        return parser

    ##Method handles ingredients addition to recipe
    @staticmethod
    def add_ingredients(recipe, ingredients):
        if ingredients is not None:
            ingredient_id_to_amount = {association["ingr_id"]: association["amount"] for association in ingredients}
            available_ingredients = Ingredient\
                .query\
                .filter(Ingredient.id.in_(','.join([str(assoc["ingr_id"]) for assoc in ingredients])))\
                .all()

            if len(ingredient_id_to_amount) != len(available_ingredients):
                abort(500, message="Not all ingredients are present in the database")

            recipe.ingredients = []

            for ingr in available_ingredients:
                assoc = IngredientAssociation()
                assoc.ingredient = ingr
                assoc.amount = ingredient_id_to_amount[ingr.id]
                recipe.ingredients.append(assoc)

    ##Method handles tags addition to recipe
    @staticmethod
    def add_tags(recipe, tags):
        if tags is not None:
            recipe.tags = Tag.query.filter(Tag.id.in_(','.join([str(i) for i in tags]))).all()


##Class contains methods for Recipe with some given ID
class RecipesWithId(Resource):

    ##Method handles GET request
    def get(self, recipe_id):
        return RecipesWithId.get_recipe_by_id(recipe_id).to_json()

    ##Methods allow to delete recipe from database, handles DELETE request
    @lm.auth_required
    def delete(self, recipe_id):

        recipe = RecipesWithId.get_recipe_by_id(recipe_id)

        try:
            app.db.session.delete(recipe)
            app.db.session.commit()
        except:
            app.db.session.rollback()
            return Flavority.failure()

        return Flavority.success()

    ##Method handles PUT request
    @lm.auth_required
    def put(self, recipe_id):

        recipe = RecipesWithId.get_recipe_by_id(recipe_id)

        args = RecipesWithId.get_form_parser().parse_args()

        RecipesWithId.update_if_set(recipe, args, 'dish_name')
        RecipesWithId.update_if_set(recipe, args, 'recipe_text')
        RecipesWithId.update_if_set(recipe, args, 'preparation_time')
        RecipesWithId.update_if_set(recipe, args, 'portions')
        Recipes.add_tags(recipe, args.tags)
        Recipes.add_ingredients(recipe, args.ingredients)

        # TODO: add rest of the arguments

        try:
            app.db.session.commit()
        except:
            traceback.print_exc()
            app.db.session.rollback()
            return Flavority.failure(), 500

        return Flavority.success()

    ##Method handles options for requests
    def options(self, recipe_id=None):
        return None

    ##Method should return one recipe with given id
    #May return 404 error if there is no recipe with given ID.
    @staticmethod
    def get_recipe_by_id(recipe_id):
        try:
            return Recipe.query.filter(Recipe.id == recipe_id).one()
        except:
            abort(404, message="Recipe with id {} doesn't exist".format(recipe_id))

    ##Method sets given argument to recipe's field
    @staticmethod
    def update_if_set(recipe, args, field):
        field_value = getattr(args, field)
        if field_value is not None:
            setattr(recipe, field, field_value)

    ##Method handles getting values from parser
    @staticmethod
    def get_form_parser():
        parser = reqparse.RequestParser()
        parser.add_argument('dish_name', type=str, help="dish name")
        parser.add_argument('recipe_text', type=str, help="recipe text")
        parser.add_argument('preparation_time', type=int, help="preparation time")
        parser.add_argument('portions', type=int, help="portions")
        parser.add_argument('tags', type=int, help="tags", action="append")
        parser.add_argument('ingredients', type=list, help="ingredients")

        return parser

    ##Method should return a set of recipes with given list of tags
    #May return 404 if it doesn't find anything
    @staticmethod
    def get_recipe_with_tags(tag_list):
        if len(tag_list) > 0:
            try:
                return Recipe.query.join(tag_assignment).filter(tag_assignment.tag.in_(tag_list)).all()
            except:
                abort(404, message="No recipes with given tags!")
        else:
            return -1       #Error!


    # @staticmethod
    # def get_recipe_with_ingredients(ingredient_list):
    #     if len(ingredient_list) > 0:
    #         try:
    #             return Recipe.query.join(ingredient_assignment).filter(ingredient_assignment.ingr.in_(ingredient_list)).all()
    #         except:
    #             abort(404, message="No recipes with given ingredients!")
    #     else:
    #         return -1       #ERROR!!
    
