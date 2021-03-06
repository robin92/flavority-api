
from base64 import b64encode, b64decode
from io import SEEK_SET
from tempfile import NamedTemporaryFile

from flask import abort, send_file
from flask.ext.restful import Resource, reqparse
from sqlalchemy.exc import SQLAlchemyError
from wand.image import Image

from . import app, lm
from .models import Photo, Recipe, User


class PhotoResource(Resource):

    """
    This class handles request for images.
    """

    KEY_FULL_SIZE = 'full-size'
    KEY_MINI_SIZE = 'mini-size'

    @staticmethod
    def convert_image(image, format=Photo.FORMAT):
        return image.convert(format)

    @staticmethod
    def encode_image(image_binary, mini_size=(300, 300)):
        assert isinstance(image_binary, bytes)

        with Image(blob=image_binary) as image:
            if image.format.lower() != format:
                image = PhotoResource.convert_image(image)
            mini_img = image.clone()
            mini_img.resize(*mini_size)
            full, mini = image.make_blob(), mini_img.make_blob()

        return {
            PhotoResource.KEY_FULL_SIZE: full,
            PhotoResource.KEY_MINI_SIZE: mini,
        }

    @staticmethod
    def parse_get_arguments():
        def cast_mini(x):
            if x.lower() == '': return True
            elif x.lower() == 'false': return False
            elif x.lower() == 'true': return True
            try:
                return bool(x)
            except ValueError:
                return False

        parser = reqparse.RequestParser()
        parser.add_argument('mini', type=cast_mini)
        return parser.parse_args()

    @staticmethod
    def parse_post_arguments():
        parser = reqparse.RequestParser()
        parser.add_argument('file', required=True, location='files')
        parser.add_argument('recipe_id', type=int)
        parser.add_argument('user_id', type=int)
        return parser.parse_args()

    @staticmethod
    def parse_put_arguments():
        parser = reqparse.RequestParser()
        parser.add_argument('file', required=True, location='files')
        return parser.parse_args()

    def options(self, photo_id=None):
        return None

    def get(self, photo_id=None):
        """
        Returns a Base64 encoded JPEG image with supplied id from database.

        If such an row doesn't exists or supplied id is `None` than HTTP404 will be
        returned.

        If request has a `mini` GET parameter then it will return image's miniature.
        """

        if photo_id is None:
            return abort(404)

        args = self.parse_get_arguments()
        image = Photo.query.get(photo_id)
        if image is None:
            return abort(404)

        file = NamedTemporaryFile(prefix='img{}'.format(photo_id), suffix='.jpg', dir=app.config['TEMPDIR'])
        file.write(b64decode(image.full_data if not args['mini'] else image.mini_data))
        file.seek(0, SEEK_SET)

        return send_file(file, mimetype='image/jpeg')

    @lm.auth_required
    def post(self, photo_id=None):
        """
        Inserts new image to the database.

        This method expects two additional arguments:
        + `file` - an image file transmitted with a request
        and one of the following
        + `recipe_id` - id of a recipe which owns the image
        + `user_id` - id of a user to whom this image should be attached as an avatar
        Method returns a dictionary with a id of just created row.

        This method can be used only when no `photo_id` is specified. In other case
        HTTP405 is returned. It may also return HTTP500 when adding to the database
        fails.
        """

        if photo_id is not None:
            return abort(405)

        args, user = self.parse_post_arguments(), lm.get_current_user()
        file_bytes = args['file'].read()
        files = PhotoResource.encode_image(file_bytes)

        photo = Photo()
        photo.full_data = b64encode(files[self.KEY_FULL_SIZE])
        photo.mini_data = b64encode(files[self.KEY_MINI_SIZE])

        if args.recipe_id is not None:
            photo.recipe = Recipe.query.get(args['recipe_id'])
        if args.user_id is not None:
            photo.avatar_user = User.query.get(args['user_id'])

        try:
            app.db.session.add(photo)
            app.db.session.commit()
        except SQLAlchemyError as e:
            app.logger.error(e)
            app.db.session.rollback()
            return abort(500)

        return {
            'id': photo.id
        }

    @lm.auth_required
    def put(self, photo_id=None):
        """
        This method updates only avatar images (changes image data).

        :param photo_id: id of a photo to update
        """
        
        if photo_id is None: return abort(405)

        args, user = self.parse_put_arguments(), lm.get_current_user()
        file_bytes = args.file.read()
        files = PhotoResource.encode_image(file_bytes)

        photo = Photo.query.get(photo_id)
        if photo is None: return abort(404)
        if photo.avatar_user is not None and photo.avatar_user != user: return abort(403)

        photo.full_data = b64encode(files[self.KEY_FULL_SIZE])
        photo.mini_data = b64encode(files[self.KEY_MINI_SIZE])

        try:
            app.db.session.commit()
        except SQLAlchemyError as e:
            app.logger.error(e)
            app.db.session.rollback()
            return abort(500)

        return {
            'id': photo.id
        }

    @lm.auth_required
    def delete(self, photo_id=None):
        """
        This method deletes only avatar images.

        :param photo_id: id of a photo to delete
        """

        if photo_id is None: return abort(405)

        photo, user = Photo.query.get(photo_id), lm.get_current_user()
        if photo is None: return abort(404)

        if photo.avatar_user_id != user.id: return abort(403)

        try:
            app.db.session.delete(photo)
            app.db.session.commit()
        except SQLAlchemyError as e:
            app.logger.error(e)
            app.db.session.rollback()
            return abort(500)

        return None, 204


__all__ = ['PhotoResource']
