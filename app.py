# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 版本: 13.0 - 历史记录功能实装！
# 描述: 新增了 /api/history 接口，允许登录用户获取自己的创作记录。
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
You are a character-driven storyteller and a master of literary analysis. Your highest priority is maintaining character integrity. Your goal is to generate a plot outline that feels like it was written by someone who has loved these characters for years.
# CORE DIRECTIVES - YOU MUST FOLLOW THESE RULES
1.  **NO OOC (Out Of Character) ACTIONS**: This is the most critical rule. Before writing, deeply analyze the provided character descriptions. Every action, decision, and reaction in the plot MUST be a believable extension of their established personality, history, and motivations. Do not make them do things that contradict their core traits for the sake of plot convenience. A single OOC moment is a total failure.
2.  **ANALYZE, THEN WRITE**: Your internal process must be: First, read and understand Character 1 and Character 2. Identify their key personality traits (e.g., "charismatic but haunted," "kind-hearted and unwavering"). Second, generate the plot outline ensuring every step is consistent with these traits.
3.  **PRONOUN ACCURACY**: Pay close attention to gender cues in the character descriptions (e.g., "male", "female", "boy", "girl") and use the correct pronouns throughout the entire outline. Misgendering a character is a critical failure.
4.  **SHOW, DON'T TELL**: Instead of saying a character is sad, describe an action that shows their sadness. Focus on emotional tension and subtle character interactions.
# TASK
Generate a detailed plot outline **{output_language_instruction}** based on the following information.
**Character 1:** {char1}
**Character 2:** {char2}
**Core Plot Prompt:** {plot_prompt}
# OUTPUT FORMAT
Please generate a detailed plot outline with the following sections:
1.  **Opening:** How the story begins.
2.  **Inciting Incident:** The event that kicks off the main plot.
3.  **Rising Action:** A series of events that build tension.
4.  **Climax:** The turning point of the story.
5.  **Falling Action:** The immediate aftermath of the climax.
6.  **Resolution:** The conclusion of the story.
Remember: The quality of this outline is judged solely on its emotional resonance and strict adherence to the characters as described. Do not break character.
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
    return jsonify({ "status": "online", "message": "Welcome to Plot Ark Backend!", "version": "13.0" })

# ... (注册和登录接口保持不变) ...
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password: return jsonify({'message': '邮箱和密码不能为空!'}), 400
    if User.query.filter_by(email=email).first(): return jsonify({'message': '该邮箱已被注册!'}), 409
    hashed_password = generate_password_hash(password, method='pbkdf2:sha266')
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

# --- ✨ 新增：获取历史记录的 API ✨ ---
@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user):
    try:
        # 从数据库中查询属于当前用户的所有记录，并按创建时间倒序排列
        prompts = Prompt.query.filter_by(user_id=current_user.id).order_by(Prompt.created_at.desc()).all()
        
        # 将查询结果格式化成一个列表
        history_list = []
        for p in prompts:
            history_list.append({
                'id': p.id,
                'character1_setting': p.character1_setting,
                'character2_setting': p.character2_setting,
                'core_prompt': p.core_prompt,
                'generated_outline': p.generated_outline,
                'created_at': p.created_at.isoformat() # 转换成标准时间格式
            })
            
        return jsonify(history_list)
        
    except Exception as e:
        print(f"!!! Error fetching history for user {current_user.email}: {e} !!!")
        return jsonify({"error": "Failed to fetch history."}), 500


# ... (generate 和 generate-guest 接口保持不变) ...
@app.route('/api/generate', methods=['POST'])
@token_required
def generate_plot_outline_for_user(current_user):
    try:
        data = request.get_json()
        char1, char2, plot_prompt, language = data.get('character1'), data.get('character2'), data.get('plot_prompt'), data.get('language', 'en')
        generated_text, error_info = get_ai_outline(char1, char2, plot_prompt, language)
        if error_info: return jsonify(error_info), 400
        new_prompt_record = Prompt(user_id=current_user.id, character1_setting=char1, character2_setting=char2, core_prompt=plot_prompt, generated_outline=generated_text)
        db.session.add(new_prompt_record)
        db.session.commit()
        return jsonify({"outline": generated_text})
    except Exception as e:
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/api/generate-guest', methods=['POST'])
def generate_plot_outline_for_guest():
    try:
        data = request.get_json()
        char1, char2, plot_prompt, language = data.get('character1'), data.get('character2'), data.get('plot_prompt'), data.get('language', 'en')
        generated_text, error_info = get_ai_outline(char1, char2, plot_prompt, language)
        if error_info: return jsonify(error_info), 400
        return jsonify({"outline": generated_text})
    except Exception as e:
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)






