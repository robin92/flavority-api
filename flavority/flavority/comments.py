
from flask.ext.restful import Resource, reqparse
from flask_restful import abort
from sqlalchemy.exc import SQLAlchemyError

from . import lm, app
from .models import Comment, Recipe
from .util import Flavority


class Comments(Resource):

    @staticmethod
    def get_form_parser():
        parser = reqparse.RequestParser()
        parser.add_argument('id', type=int, requred=True, help="comment id")
        parser.add_argument('author_id', type=int, required=True, help="comment author id")
        parser.add_argument('recipe_id', type=int, required=True, help="comment recipe id")
        parser.add_argument('text', type=str, required=True, help="comment text")
        parser.add_argument('difficulty', type=float, required=False, help="given difficulty")
        parser.add_argument('taste', type=float, required=False, help="given taste")

        return parser

    @staticmethod
    def parse_get_arguments():
        parser = reqparse.RequestParser()
        parser.add_argument('recipe_id', type=int, default=None)
        parser.add_argument('page', type=int, default=0)
        parser.add_argument('limit', type=int, default=10)
        return parser.parse_args()

    #Implemented to get all User's comments
    @staticmethod
    def get_author_comments(author_id):
        try:
            return Comment.query.filter(Comment.author_id == author_id)
        except:
            abort(404, message="Author with id: {} has no comments!".format(author_id))

    #Implemented to get all Recipe's comments
    @staticmethod
    def get_recipe_comments(recipe_id):
        try:
            return Comment.query.filter(Comment.recipe_id == recipe_id)
        except:
            abort(404, message="Recipe with id: {} has no comments yet!".format(recipe_id))

    #Implemented to get specific comment with given comment_id, author_id and recipe_id
    @staticmethod
    def get_comment(comment_id, author_id, recipe_id):
        try:
            return Comment.query.filter(Comment.id == comment_id, Comment.author_id == author_id, Comment.recipe_id == recipe_id).one()
        except:
            abort(404, message="Comment with id: {} does not exist!".format(comment_id))

    #TODO: Implementation of comment_post() method

    #Method handles comment deletion
    @lm.auth_required
    def delete(self, comment_id, author_id, recipe_id):
        comment_to_delete = self.get_comment(comment_id, author_id, recipe_id) #If someone's user_id is different from author's id then \
                # comment shouldn't be found because comment_id was given
        try:
            app.db.session.delete(comment_to_delete)
            app.db.session.commit()
        except SQLAlchemyError:
            app.db.session.rollback()
            return Flavority.failure()
        return Flavority.success()

    #Method handles comment edition
    @lm.auth_required
    def edit(self, comment_id, new_text):   #zakladam, ze nie mozna zmienic oceny tylko sam tekst komentarza!!
        comment = self.get_comment(comment_id)      #same note as in $delete$ method -> will search for proper comment (only author can edit)
        comment.text = new_text
        try:
            app.db.session.commit()
        except SQLAlchemyError:
            app.db.session.rollback()
            return Flavority.failure()
        return Flavority.success()

    def options(self):
        return None
        
    def get(self):
        args = self.parse_get_arguments()

        query1 = Comment.query
        query2 = Comment.query
        if args['recipe_id'] is not None:
            query1 = Recipe.query.get(args['recipe_id']).comments.slice(args['page']*args['limit'], (1+args['page'])*args['limit'])
            query2 = Recipe.query.get(args['recipe_id']).comments  
                 
        return {
            'comments': [ c.to_json() for c in query1.all() ],
            'all': query2.count()
        }
