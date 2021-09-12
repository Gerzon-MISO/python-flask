from flask import request,jsonify
from marshmallow.exceptions import ValidationError
import redis
from datetime import timedelta
from ..modelos import db, Cancion, CancionSchema, Usuario, UsuarioSchema, Album, AlbumSchema
from flask_restful import Resource
from sqlalchemy.exc import IntegrityError
from flask_jwt_extended import jwt_required, create_access_token,get_jwt,get_jwt_identity,JWTManager
from ..helpers import validarPass,validarUsuario,noCompartirUsuarioCreador,puedeDetallarAlbum

jwt=JWTManager()
cancion_schema = CancionSchema()
usuario_schema = UsuarioSchema()
album_schema = AlbumSchema()

jwt_redis_blocklist = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    token_in_redis = jwt_redis_blocklist.get(jti)
    return token_in_redis is not None

def withoutPass(usuario):
    contrasena,rest = (lambda contrasena, **rest: (contrasena, rest))(**usuario)
    return rest

class VistaCanciones(Resource):
    @jwt_required()
    def post(self,id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            nueva_cancion = Cancion(titulo=request.json["titulo"], minutos=request.json["minutos"], segundos=request.json["segundos"], interprete=request.json["interprete"])
            db.session.add(nueva_cancion)
            db.session.commit()
            return cancion_schema.dump(nueva_cancion)
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401
    @jwt_required()
    def get(self,id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            return [cancion_schema.dump(ca) for ca in Cancion.query.all()]  
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaCancion(Resource):
    @jwt_required()
    def get(self,id_usuario,id_cancion):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            return cancion_schema.dump(Cancion.query.get_or_404(id_cancion)) 
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

    @jwt_required()
    def put(self,id_usuario,id_cancion):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            cancion = Cancion.query.get_or_404(id_cancion)
            cancion.titulo = request.json.get("titulo",cancion.titulo)
            cancion.minutos = request.json.get("minutos",cancion.minutos)
            cancion.segundos = request.json.get("segundos",cancion.segundos)
            cancion.interprete = request.json.get("interprete",cancion.interprete)
            db.session.commit()
            return cancion_schema.dump(cancion)
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

    @jwt_required()
    def delete(self,id_usuario,id_cancion):

        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            cancion = Cancion.query.get_or_404(id_cancion)
            db.session.delete(cancion)
            db.session.commit()
            return '',204
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaAlbumesCanciones(Resource):
    @jwt_required()
    def get(self,id_usuario,id_cancion):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            cancion = Cancion.query.get_or_404(id_cancion)
            return [album_schema.dump(al) for al in cancion.albumes]
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaSignIn(Resource):
    
    def post(self):
        nuevo_usuario = Usuario(nombre=request.json["nombre"], contrasena=request.json["contrasena"])
        db.session.add(nuevo_usuario)
        db.session.commit()
        token_de_acceso = create_access_token(identity = nuevo_usuario.id)
        return {"mensaje":"usuario creado exitosamente", "token":token_de_acceso}

    @jwt_required()
    def put(self, id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            usuario = Usuario.query.get_or_404(id_usuario)
            usuario.contrasena = request.json.get("contrasena",usuario.contrasena)
            db.session.commit()
            return usuario_schema.dump(usuario)
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

    @jwt_required()
    def delete(self, id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            usuario = Usuario.query.get_or_404(id_usuario)
            db.session.delete(usuario)
            db.session.commit()
            return '',204
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaLogIn(Resource):

    def post(self):
        try:
            usuario = Usuario.query.filter(Usuario.nombre == request.json["nombre"]).first()
            if usuario is None:
                return {"mensaje":"El usuario no existe"}, 404
            else:
                validarPass(usuario.contrasena,request.json["contrasena"])
                token_de_acceso = create_access_token(identity = usuario.id)
                return {"mensaje":"Inicio de sesión exitoso", "token": token_de_acceso}
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaLogOut(Resource):
    @jwt_required()
    def post(self,id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            jti = get_jwt()["jti"]
            jwt_redis_blocklist.set(jti, "", ex=timedelta(hours=1))
            respuesta= jsonify({"mensaje":"Se ha desconectado correctamente"})
            return respuesta
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaAlbumsUsuario(Resource):

    @jwt_required()
    def post(self, id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            nuevo_album = Album(titulo=request.json["titulo"], anio=request.json["anio"], descripcion=request.json["descripcion"], medio=request.json["medio"])
            usuario = Usuario.query.get_or_404(id_usuario)
            nuevo_album.usuario_creador=usuario.id
            db.session.add(nuevo_album)
            db.session.commit()
            return album_schema.dump(nuevo_album)
        except (IntegrityError,ValidationError) as e:
            if isinstance(e,ValidationError):
                return {"mensaje":e.messages[0]},401
            else:
                return {"mensaje":'El usuario ya tiene un album con dicho nombre'},409

    @jwt_required()
    def get(self, id_usuario):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            usuario = Usuario.query.get_or_404(id_usuario)
            totalAlbum = usuario.albums + usuario.albumescompartidos
            return [album_schema.dump(al) for al in totalAlbum]
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaCancionesAlbum(Resource):
    @jwt_required()
    def post(self,id_usuario,id_album):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            album = Album.query.get_or_404(id_album)
            
            if "id_cancion" in request.json.keys():
                
                nueva_cancion = Cancion.query.get(request.json["id_cancion"])
                if nueva_cancion is not None:
                    album.canciones.append(nueva_cancion)
                    db.session.commit()
                else:
                    return 'Canción errónea',404
            else: 
                nueva_cancion = Cancion(titulo=request.json["titulo"], minutos=request.json["minutos"], segundos=request.json["segundos"], interprete=request.json["interprete"])
                album.canciones.append(nueva_cancion)
            db.session.commit()
            return cancion_schema.dump(nueva_cancion)
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

    @jwt_required()      
    def get(self,id_usuario,id_album):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            album = Album.query.get_or_404(id_album)
            return [cancion_schema.dump(ca) for ca in album.canciones]
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaAlbum(Resource):
    @jwt_required()
    def get(self,id_usuario,id_album):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            albumDetallar = Album.query.get_or_404(id_album)
            puedeDetallarAlbum(get_jwt_identity(),albumDetallar.usuario_creador,albumDetallar.usuarioscompartidos)
            return album_schema.dump(albumDetallar)
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401
    @jwt_required()
    def put(self,id_usuario,id_album):
        try: 
            validarUsuario(get_jwt_identity(),id_usuario)

            album = Album.query.get_or_404(id_album)
            album.titulo = request.json.get("titulo",album.titulo)
            album.anio = request.json.get("anio", album.anio)
            album.descripcion = request.json.get("descripcion", album.descripcion)
            album.medio = request.json.get("medio", album.medio)
            if(request.json['usuarioscompartidos'] is not None):
                noCompartirUsuarioCreador(album.usuario.id,request.json['usuarioscompartidos'])
                usuariosReq = []
                for usuario_id in request.json['usuarioscompartidos']:
                    usuario = Usuario.query.get_or_404(usuario_id)
                    usuariosReq.append(usuario)
                album.usuarioscompartidos=usuariosReq
            db.session.commit()
            return album_schema.dump(album)
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401
    @jwt_required()
    def delete(self,id_usuario,id_album):
        try:
            validarUsuario(get_jwt_identity(),id_usuario)
            album = Album.query.get_or_404(id_album)
            db.session.delete(album)
            db.session.commit()
            return '',204
        except ValidationError as e:
            return {"mensaje":e.messages[0]},401

class VistaUsuarios(Resource):
    @jwt_required()
    def get(self):
        logUser = Usuario.query.get_or_404(get_jwt_identity())
        usuarios = Usuario.query.all()
        usuarios.remove(logUser)
        usuariosFormat = [usuario_schema.dump(usuario) for usuario in usuarios]
        usuariosPure = list(map(withoutPass,usuariosFormat))
        return usuariosPure