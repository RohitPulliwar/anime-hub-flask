from flask import Flask

def create_app():
    app= Flask(__name__)
    app.secret_key="mykey"

    from .routes.main_route import main_bp
    from .routes.auth_route import auth_bp
    from .routes.favorite_route import fav_bp
    from .routes.quiz_route import quiz_bp

    app.register_blueprint(quiz_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(fav_bp)

    return app