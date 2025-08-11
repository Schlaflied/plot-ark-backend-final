# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 版本: 14.0 - 自定义删除记录功能！
# 描述: 新增了 DELETE /api/history/<id> 接口，允许用户删除自己的创作记录。
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
    language_instructions = {'en': 'in English', 'zh-CN': 'in Simplified Chinese', 'zh-TW': 'in Traditional Chinese'}
    output_language_instruction = language_instructions.get(language, 'in English')
    prompt = f"""
# ROLE & GOAL
You are a character-driven storyteller... (rest of the prompt is unchanged)
"""
    model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
    safety_settings = [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    response = model.generate_content(prompt, safety_settings=safety_settings)
    if not response.parts:
        block_reason = response.prompt_feedback.block_reason.name if response.prompt_feedback else "Unknown"
        return None, { "error": "内容被安全系统拦截", "reason": f"原因: {block_reason}. 请尝试修改Prompt。" }
    return response.text, None

# --- API 路由定义 ---
@app.route('/')
def index():
    return jsonify({ "status": "online", "message": "Welcome to Plot Ark Backend!", "version": "14.0" })

# ... (注册和登录接口保持不变) ...
@app.route('/api/register', methods=['POST'])
def register():
    # ...
    return jsonify({'message': '注册成功!'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    # ...
    return jsonify({'token': token})

@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user):
    # ... (代码不变)
    prompts = Prompt.query.filter_by(user_id=current_user.id).order_by(Prompt.created_at.desc()).all()
    history_list = [{'id': p.id, 'character1_setting': p.character1_setting, 'character2_setting': p.character2_setting, 'core_prompt': p.core_prompt, 'generated_outline': p.generated_outline, 'created_at': p.created_at.isoformat()} for p in prompts]
    return jsonify(history_list)

# --- ✨ 新增：删除历史记录的 API ✨ ---
@app.route('/api/history/<int:prompt_id>', methods=['DELETE'])
@token_required
def delete_history_item(current_user, prompt_id):
    try:
        # 在数据库中查找对应的记录
        prompt_to_delete = Prompt.query.get(prompt_id)
        
        # 安全检查：如果记录不存在，或者记录不属于当前用户，则返回错误
        if not prompt_to_delete:
            return jsonify({"error": "记录未找到。"}), 404
        if prompt_to_delete.user_id != current_user.id:
            return jsonify({"error": "无权删除此记录。"}), 403 # 403 Forbidden
            
        # 删除记录并提交
        db.session.delete(prompt_to_delete)
        db.session.commit()
        
        print(f"--- History item {prompt_id} DELETED for user: {current_user.email} ---")
        return jsonify({"message": "记录已成功删除。"}), 200
        
    except Exception as e:
        print(f"!!! Error deleting history for user {current_user.email}: {e} !!!")
        return jsonify({"error": "删除记录时发生错误。"}), 500


# ... (generate 和 generate-guest 接口保持不变) ...
@app.route('/api/generate', methods=['POST'])
@token_required
def generate_plot_outline_for_user(current_user):
    # ...
    return jsonify({"outline": generated_text})

@app.route('/api/generate-guest', methods=['POST'])
def generate_plot_outline_for_guest():
    # ...
    return jsonify({"outline": generated_text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)







