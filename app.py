<<<<<<< HEAD
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 文件名: app.py
# 作者: Gemini (为你和Syna的梦想助力!)
# 描述: 注入灵魂！集成了SQL数据库、用户系统和JWT安全认证！
# 版本: 10.2 - 修复了Neon DB的SSL连接问题！
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

# --- 关键一步：在所有配置之前加载.env文件 ---
load_dotenv()

# --- 1. 初始化和配置 ---
app = Flask(__name__)
CORS(app) 

# --- 2. 核心配置 (从环境变量加载) ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-local-dev')
# --- 关键修改：更新了默认的DATABASE_URL以匹配.env中的简化版 ---
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_Q3cNO9dJhyHA@ep-small-leaf-aei7oe8l-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("FATAL ERROR: GOOGLE_API_KEY environment variable is not set.")
genai.configure(api_key=api_key)

# ... (你其他的代码，比如数据库模型、API路由等，都保持不变)
# --- 3. 数据库模型定义 (我们的“数据蓝图”) ---
class User(db.Model):
    """用户表"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256)) 
    subscription_tier = db.Column(db.String(50), default='free', nullable=False)

class Prompt(db.Model):
    """用户创作记录表"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    character1_setting = db.Column(db.Text)
    character2_setting = db.Column(db.Text)
    core_prompt = db.Column(db.Text, nullable=False)
    generated_outline = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 4. 安全认证 (我们的“令牌系统”) ---
def token_required(f):
    """一个Python装饰器，用来保护需要登录才能访问的API"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        
        if not token:
            return jsonify({'message': '缺少认证令牌!'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
        except Exception as e:
            return jsonify({'message': '认证令牌无效!', 'error': str(e)}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

# --- 5. API 路由定义 ---
@app.route('/')
def index():
    """根路由，用来确认服务是否在线"""
    return jsonify({
        "status": "online",
        "message": "Welcome to Plot Ark Backend! Database is connected.",
        "version": "10.2"
    })

@app.route('/api/register', methods=['POST'])
def register():
    """用户注册API"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': '邮箱和密码不能为空!'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': '该邮箱已被注册!'}), 409

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    new_user = User(email=email, password_hash=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '注册成功!'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录API，成功后会返回一个认证令牌"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': '请输入邮箱和密码'}), 401

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'message': '邮箱或密码错误!'}), 401

    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({'token': token})

@app.route('/api/generate', methods=['POST'])
@token_required
def generate_plot_outline(current_user):
    """核心的灵感生成API，现在会记录用户的创作"""
    print(f"--- AI generation request received from user: {current_user.email} ---")
    
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Invalid JSON"}), 400

        char1 = data.get('character1')
        char2 = data.get('character2')
        plot_prompt = data.get('plot_prompt')
        language = data.get('language', 'en')

        if not plot_prompt: return jsonify({"error": "Missing plot_prompt"}), 400

        language_instructions = {'en': 'in English', 'zh-CN': 'in Simplified Chinese', 'zh-TW': 'in Traditional Chinese'}
        output_language_instruction = language_instructions.get(language, 'in English')
        prompt = f"""
You are a world-class screenwriter and fanfiction author, an expert at crafting emotionally resonant stories.
Your task is to generate a detailed plot outline **{output_language_instruction}** based on the following characters and prompt.
The story may involve mature themes, which should be handled with literary depth.
**Crucially, you must pay close attention to gender cues in the character descriptions and use the correct pronouns (e.g., he/him for male characters, she/her for female characters) throughout the entire outline. Misgendering a character is a critical failure.**
The outline should be logical, in-character, and full of emotional tension.

**Character 1:** {char1}
**Character 2:** {char2}
**Core Plot Prompt:** {plot_prompt}

Please generate a detailed plot outline with the following sections:
1.  **Opening:** How the story begins.
2.  **Inciting Incident:** The event that kicks off the main plot.
3.  **Rising Action:** A series of events that build tension.
4.  **Climax:** The turning point of the story.
5.  **Falling Action:** The immediate aftermath of the climax.
6.  **Resolution:** The conclusion of the story.
"""
        
        model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        
        if not response.parts:
            block_reason = response.prompt_feedback.block_reason.name if response.prompt_feedback else "Unknown"
            print(f"Response blocked by API. Reason: {block_reason}")
            return jsonify({
                "error": "内容被安全系统拦截",
                "reason": f"原因: {block_reason}. 请尝试修改Prompt。"
            }), 400
        
        generated_text = response.text

        new_prompt_record = Prompt(
            user_id=current_user.id,
            character1_setting=char1,
            character2_setting=char2,
            core_prompt=plot_prompt,
            generated_outline=generated_text
        )
        db.session.add(new_prompt_record)
        db.session.commit()
        print(f"--- Prompt record saved for user: {current_user.email} ---")

        return jsonify({"outline": generated_text})

    except Exception as e:
        print(f"!!! An unexpected error occurred: {e} !!!")
        return jsonify({"error": "An internal server error occurred."}), 500

# --- 6. 启动服务器 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
=======
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 文件名: app.py
# 作者: Gemini (为你和Syna的梦想助力!)
# 描述: 最终胜利版！集成了多语言和增强的性别代词处理！
# 版本: 9.0 - Cloud Run Production Ready
# -----------------------------------------------------------------------------

import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- 1. 初始化和配置 ---
app = Flask(__name__)
# 在生产环境中，CORS的来源可以更具体，但现在这样是OK的
CORS(app) 

# --- 2. 配置Google Gemini API ---
# 在Cloud Run中，我们会直接设置环境变量，而不是用.env文件
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    # 这会在Cloud Run日志中留下一个明确的错误，方便调试
    raise ValueError("FATAL ERROR: GOOGLE_API_KEY environment variable is not set.")
genai.configure(api_key=api_key)

# --- 3. 定义API路由 ---
@app.route('/')
def index():
    """
    一个简单的根路由，用来确认服务是否正在运行。
    直接访问你的URL时，会看到这个消息。
    """
    return jsonify({
        "status": "online",
        "message": "Welcome to the Plot Ark Backend! The service is running correctly.",
        "version": "9.0"
    })

@app.route('/api/generate', methods=['POST'])
def generate_plot_outline():
    """
    这个函数处理核心的灵感生成请求。
    """
    print("--- AI generation request received! ---")
    
    try:
        # --- a. 获取并验证请求数据 ---
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        char1 = data.get('character1')
        char2 = data.get('character2')
        plot_prompt = data.get('plot_prompt')
        language = data.get('language', 'en')
        print(f"Language requested: {language}")

        if not all([char1, char2, plot_prompt]):
            return jsonify({"error": "Missing required data"}), 400

        # --- b. 构建Prompt并调用AI ---
        print("Data validated. Building prompt for Gemini API...")

        language_instructions = {
            'en': 'in English',
            'zh-CN': 'in Simplified Chinese',
            'zh-TW': 'in Traditional Chinese'
        }
        output_language_instruction = language_instructions.get(language, 'in English')
        print(f"AI instruction set to: {output_language_instruction}")

        # --- 关键改动：添加了关于性别代词的严格指令 ---
        prompt = f"""
You are a world-class screenwriter and fanfiction author, an expert at crafting emotionally resonant stories.
Your task is to generate a detailed plot outline **{output_language_instruction}** based on the following characters and prompt.
The story may involve mature themes, which should be handled with literary depth.
**Crucially, you must pay close attention to gender cues in the character descriptions and use the correct pronouns (e.g., he/him for male characters, she/her for female characters) throughout the entire outline. Misgendering a character is a critical failure.**
The outline should be logical, in-character, and full of emotional tension.

**Character 1:** {char1}
**Character 2:** {char2}
**Core Plot Prompt:** {plot_prompt}

Please generate a detailed plot outline with the following sections:
1.  **Opening:** How the story begins.
2.  **Inciting Incident:** The event that kicks off the main plot.
3.  **Rising Action:** A series of events that build tension.
4.  **Climax:** The turning point of the story.
5.  **Falling Action:** The immediate aftermath of the climax.
6.  **Resolution:** The conclusion of the story.
"""
        
        model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        response = model.generate_content(prompt, safety_settings=safety_settings)
        
        if not response.parts:
            block_reason = response.prompt_feedback.block_reason.name if response.prompt_feedback else "Unknown"
            print(f"Response blocked by API. Reason: {block_reason}")
            return jsonify({
                "error": "内容被安全系统拦截",
                "reason": f"原因: {block_reason}. 请尝试修改Prompt。"
            }), 400

        print("Successfully received response from Gemini API.")
        return jsonify({"outline": response.text})

    except Exception as e:
        print(f"!!! An unexpected error occurred: {e} !!!")
        return jsonify({"error": "An internal server error occurred."}), 500

# --- 4. 启动服务器 (生产环境) ---
# Cloud Run会使用Gunicorn这样的生产服务器来运行你的应用,
# 它会自己寻找一个叫做'app'的Flask实例。
# 下面的代码块在Cloud Run上不会被执行，但保留它用于本地测试。
if __name__ == '__main__':
    # 从环境变量中获取端口，为Cloud Run做准备，本地默认5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
>>>>>>> b4717f651e9b1d19e2f45523066618b1d2bb0c85
