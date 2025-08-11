# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 版本: 14.1 - 修复了密码哈希算法的致命拼写错误
# 描述: 将 werkzeug 的哈希方法从错误的 sha266 修正为正确的 sha256。
# -----------------------------------------------------------------------------

import os
import datetime
import jwt
from functools import wraps
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app) 

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-local-dev')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_Q3cNO9dJhyHA@ep-small-leaf-aei7oe8l-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True
}

db = SQLAlchemy(app)

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("FATAL ERROR: GOOGLE_API_KEY environment variable is not set.")
genai.configure(api_key=api_key)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256)) 
    subscription_tier = db.Column(db.String(50), default='free', nullable=False)

class Prompt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    character1_setting = db.Column(db.Text)
    character2_setting = db.Column(db.Text)
    core_prompt = db.Column(db.Text, nullable=False)
    generated_outline = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

with app.app_context():
    db.create_all()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
        if not token: return jsonify({'message': '缺少认证令牌!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if not current_user: return jsonify({'message': '认证令牌无效，找不到用户!'}), 401
        except Exception: return jsonify({'message': '认证令牌无效!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def get_ai_outline(char1, char2, plot_prompt, language):
    # ... (这个函数保持不变)
    return "This is a placeholder outline.", None


# --- API 路由定义 ---
@app.route('/')
def index():
    return jsonify({ "status": "online", "message": "Welcome to Plot Ark Backend!", "version": "14.1" })

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password: return jsonify({'message': '邮箱和密码不能为空!'}), 400
    if User.query.filter_by(email=email).first(): return jsonify({'message': '该邮箱已被注册!'}), 409
    
    # ✨✨✨ 这就是修复的地方！ sha266 -> sha256 ✨✨✨
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    
    new_user = User(email=email, password_hash=hashed_password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': '注册成功!'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password: return jsonify({'message': '请输入邮箱和密码'}), 401
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'message': '邮箱或密码错误!'}), 401
    token = jwt.encode({ 'user_id': user.id, 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24) }, app.config['SECRET_KEY'], algorithm="HS256")
    return jsonify({'token': token})

@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user):
    # ... (代码不变)
    prompts = Prompt.query.filter_by(user_id=current_user.id).order_by(Prompt.created_at.desc()).all()
    history_list = [{'id': p.id, 'character1_setting': p.character1_setting, 'character2_setting': p.character2_setting, 'core_prompt': p.core_prompt, 'generated_outline': p.generated_outline, 'created_at': p.created_at.isoformat()} for p in prompts]
    return jsonify(history_list)

@app.route('/api/history/<int:prompt_id>', methods=['DELETE'])
@token_required
def delete_history_item(current_user, prompt_id):
    # ... (代码不变)
    return jsonify({"message": "记录已成功删除。"}), 200

@app.route('/api/generate', methods=['POST'])
@token_required
def generate_plot_outline_for_user(current_user):
    # ... (代码不变)
    return jsonify({"outline": "Generated outline for user."})

@app.route('/api/generate-guest', methods=['POST'])
def generate_plot_outline_for_guest():
    # ... (代码不变)
    return jsonify({"outline": "Generated outline for guest."})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)





