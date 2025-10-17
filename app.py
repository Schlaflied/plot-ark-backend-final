# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 版本: 25.3 - 最终修复版
# 描述:
# 1. 将模型恢复为项目核心 gemini-2.5-pro。
# 2. 修正了 app.run 中 host 参数的致命拼写错误 ('0.logg.0' -> '0.0.0.0')。
# 下一步的关键是在 Cloud Run 中设置"最小实例"为 1 来彻底解决冷启动超时问题。
# -----------------------------------------------------------------------------
import os
import datetime
import jwt
import traceback
from functools import wraps

import google.generativeai as genai
from flask import Flask, request, jsonify, url_for, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# from flask_mail import Mail, Message


# --- 1. 初始化与配置 ---
load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- 核心配置 ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-local-dev')
app.config['ADMIN_SECRET_TOKEN'] = os.environ.get('ADMIN_SECRET_TOKEN', 'a-super-secret-admin-token-for-n8n')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://user:password@host:port/dbname')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}

# --- 限流器配置 ---
limiter = Limiter(
    app=app, # 明确指定app为关键字参数
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"], # 全局默认限流
    storage_uri="memory://", # 使用内存存储，注意Cloud Run多实例时的局限性
)


# --- 数据库与模型定义 ---
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    credits = db.Column(db.Integer, nullable=False, default=0)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    subscription_tier = db.Column(db.String(50), nullable=True, default='free')

class Prompt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    character1_setting = db.Column(db.Text)
    character2_setting = db.Column(db.Text)
    core_prompt = db.Column(db.Text, nullable=False)
    generated_outline = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class StoryOutline(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    characters = db.Column(db.Text, nullable=True)
    core_scenes = db.Column(db.Text, nullable=True)
    outline = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

with app.app_context():
    db.create_all()


# --- API 密钥配置 ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ Gemini API 密钥配置成功！")
    else:
        print("⚠️ 警告：GOOGLE_API_KEY 环境变量未设置。AI生成功能将不可用。")
except Exception as e:
    print(f"❌ Gemini API 密钥配置失败: {e}")


# --- 2. 辅助函数与装饰器 ---
def make_error_response(error_type, message, status_code):
    response = jsonify(error=error_type, message=message)
    response.status_code = status_code
    return response

def send_verification_email(user_email, token, language='en'):
    # serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    # token = serializer.dumps(user_email, salt='email-confirm-salt') # Token is now passed directly
    verification_url = url_for('verify_email_token', token=token, _external=True)

    email_content_templates = {
        'en': {
            'subject': "Verify your Plot Ark Account Email",
            'html_content': f"""<html><body>
                <h2>Welcome to Plot Ark!</h2>
                <p>Thank you for registering. Please click the button below to activate your account and receive free creation credits.</p>
                <a href=\"{verification_url}\" target=\"_blank\" style=\"font-size: 16px; font-family: Helvetica, Arial, sans-serif; color: #ffffff; text-decoration: none; background-color: #007bff; border-radius: 5px; padding: 10px 20px; display: inline-block;\">Activate Account</a>
                <p style=\"margin-top: 20px; font-size: 12px; color: #888;\">If you did not request to register for Plot Ark, please ignore this email.</p>
                </body></html>"""
        },
        'zh-CN': {
            'subject': "请验证您的 Plot Ark 账户邮箱",
            'html_content': f"""<html><body>
                <h2>欢迎来到 Plot Ark！</h2>
                <p>感谢您的注册。请点击下方的按钮来激活您的账户，领取免费创作点数。</p>
                <a href=\"{verification_url}\" target=\"_blank\" style=\"font-size: 16px; font-family: Helvetica, Arial, sans-serif; color: #ffffff; text-decoration: none; background-color: #007bff; border-radius: 5px; padding: 10px 20px; display: inline-block;\">激活账户</a>
                <p style=\"margin-top: 20px; font-size: 12px; color: #888;\">如果您没有请求注册 Plot Ark，请忽略此邮件。</p>
                </body></html>"""
        },
        'zh-TW': {
            'subject': "請驗證您的 Plot Ark 帳戶信箱",
            'html_content': f"""<html><body>
                <h2>歡迎來到 Plot Ark！</h2>
                <p>感謝您的註冊。請點擊下方的按鈕來啟用您的帳戶，領取免費創作點數。</p>
                <a href=\"{verification_url}\" target=\"_blank\" style=\"font-size: 16px; font-family: Helvetica, Arial, sans-serif; color: #ffffff; text-decoration: none; background-color: #007bff; border-radius: 5px; padding: 10px 20px; display: inline-block;\">啟用帳戶</a>
                <p style=\"margin-top: 20px; font-size: 12px; color: #888;\">如果您沒有請求註冊 Plot Ark，請忽略此郵件。</p>
                </body></html>"""
        }
    }

    current_email_content = email_content_templates.get(language, email_content_templates['en']) # Fallback to English

    # Brevo API 配置
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = os.environ.get('BREVO_API_KEY')

    if not configuration.api_key['api-key']:
        print("!!! 邮件服务未配置：BREVO_API_KEY 环境变量未设置。邮件功能将不可用。")
        # 在开发环境中，仍然打印链接以便测试
        print(f"!!! 为 {user_email} 生成的验证链接 (仅供测试): {verification_url}")
        return False, token # Return token for testing

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

    # 邮件内容
    subject = current_email_content['subject']
    html_content = current_email_content['html_content']
    sender = {"name": "Plot Ark", "email": "noreply@plot-ark.com"} # *** 重要：请替换成您的域名 ***
    to = [{"email": user_email}]

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(to=to, html_content=html_content, sender=sender, subject=subject)

    # 发送邮件
    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"邮件已发送至 {user_email}。 Brevo响应: {api_response})")
        return True, "Verification email sent."
    except ApiException as e:
        print(f"!!! 通过Brevo发送邮件失败: {e} !!!")
        return False, str(e)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            # Fallback for requests with no token at all
            current_user = type('Guest', (), {'is_verified': True, 'credits': 3, 'id': -1, 'is_guest': True})()
            return f(current_user, *args, **kwargs)

        # Handle guest users who have a 'guest-...' token
        if token.startswith('guest-'):
            current_user = type('Guest', (), {'is_verified': True, 'credits': 3, 'id': -1, 'is_guest': True})()
            return f(current_user, *args, **kwargs)

        # Handle real, logged-in users with a JWT
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return make_error_response('user_not_found', '认证令牌无效，找不到用户', 401)
            current_user.is_guest = False
        except jwt.ExpiredSignatureError:
            return make_error_response('token_expired', '认证令牌已过期', 401)
        except jwt.InvalidTokenError:
            return make_error_response('token_invalid', '认证令牌无效', 401)
        return f(current_user, *args, **kwargs)
    return decorated

def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_token = request.headers.get('X-Admin-Token')
        if not admin_token or admin_token != app.config['ADMIN_SECRET_TOKEN']:
            return make_error_response('unauthorized', '缺少或无效的管理员令牌', 403)
        return f(*args, **kwargs)
    return decorated


# --- 3. AI 核心功能 ---
def get_ai_outline(char1, char2, plot_prompt, language):
    language_instructions = {'en': 'in English', 'zh-CN': 'in Simplified Chinese (简体中文)', 'zh-TW': 'in Traditional Chinese (繁體中文)'}
    output_language_instruction = language_instructions.get(language, 'in English')

    section_titles = {
        'en': {
            'char_analysis': 'Character Analysis',
            'plot_outline': 'Plot Outline',
            'opening': 'Opening',
            'inciting_incident': 'Inciting Incident',
            'rising_action': 'Rising Action',
            'climax': 'Climax',
            'falling_action': 'Falling Action',
            'resolution': 'Resolution',
            'char1_label': 'Character 1',
            'char2_label': 'Character 2',
        },
        'zh-CN': {
            'char_analysis': '角色性格分析',
            'plot_outline': '情节大纲',
            'opening': '开篇',
            'inciting_incident': '导火索',
            'rising_action': '发展部分',
            'climax': '高潮',
            'falling_action': '回落部分',
            'resolution': '结局',
            'char1_label': '角色1',
            'char2_label': '角色2',
        },
        'zh-TW': {
            'char_analysis': '角色性格分析', # Assuming same for now, can be adjusted if needed
            'plot_outline': '情節大綱',
            'opening': '開篇',
            'inciting_incident': '導火線',
            'rising_action': '發展部分',
            'climax': '高潮',
            'falling_action': '回落部分',
            'resolution': '結局',
            'char1_label': '角色1',
            'char2_label': '角色2',
        }
    }
    current_titles = section_titles.get(language, section_titles['en']) # Fallback to English

    prompt = f"""
# ROLE & GOAL
You are a character-driven storyteller and a master of literary analysis. Your highest priority is maintaining character integrity. Your goal is to generate a plot outline that feels like it was written by someone who has loved these characters for years, and you MUST generate it in the requested language.

# CORE DIRECTIVES - YOU MUST FOLLOW THESE RULES
1. **NO OOC (Out Of Character) ACTIONS**: This is the most critical rule. Before writing, deeply analyze the provided character descriptions. Every action, decision, and reaction in the plot MUST be a believable extension of their established personality, history, and motivations.
2. **NO CONVERSATIONAL PREAMBLE**: Do not start your response with any conversational text like "好的，我将..." or "Okay, I will...". Begin your response directly with the requested analysis.
3. **USE MARKDOWN FOR STRUCTURE**: You must use markdown for formatting as specified in the OUTPUT FORMAT section.
4. **STRICTLY ADHERE TO LANGUAGE**: Your entire output, including section titles and content, MUST be in the language specified by '{output_language_instruction}'.

# TASK
Generate a character analysis and a detailed plot outline **{output_language_instruction}** based on the following information.

**Character 1:** {char1}
**Character 2:** {char2}
**Core Plot Prompt:** {plot_prompt}

# OUTPUT FORMAT
Your output MUST be in markdown format and structured EXACTLY as follows. Ensure there is a blank line after each heading.

### {current_titles['char_analysis']}

* {current_titles['char1_label']}: [Identify Character 1's name from the input. Then, begin your analysis with the character's name followed by a comma and the analysis text.]
* {current_titles['char2_label']}: [Identify Character 2's name from the input. Then, begin your analysis with the character's name followed by a comma and the analysis text.]

### {current_titles['plot_outline']}

**1. {current_titles['opening']}:** [How the story begins]

**2. {current_titles['inciting_incident']}:** [The event that kicks off the main plot]

**3. {current_titles['rising_action']}:** [A series of events that build tension]

**4. {current_titles['climax']}:** [The turning point of the story]

**5. {current_titles['falling_action']}:** [The immediate aftermath of the climax]

**6. {current_titles['resolution']}:** [The conclusion of the story]
"""
    try:
        # ✅ --- 恢复使用核心模型 ---
        model = genai.GenerativeModel('models/gemini-2.5-pro')
        safety_settings = [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        response = model.generate_content(prompt, safety_settings=safety_settings)

        if not response.parts:
            block_reason_detail = "Unknown"
            if response.prompt_feedback and hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                block_reason_detail = response.prompt_feedback.block_reason.name
            return None, {"error": "内容被安全系统拦截", "reason": f"原因: {block_reason_detail}. 请尝试修改Prompt。"}

        return response.text, None
    except Exception as e:
        print(f"!!! AI 调用失败: {e} !!!"); print(traceback.format_exc())
        return None, {"error": "AI 服务调用时发生内部错误", "reason": str(e)}


# --- 4. API 路由定义 ---
@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "message": "Welcome to Plot Ark Backend!",
        "version": "25.3 Final-Fixed"
    })

@app.route('/api/register', methods=['POST'])
def register():
    # ... (代码不变)
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return make_error_response('missing_credentials', '邮箱和密码不能为空', 400)

    if User.query.filter_by(email=email).first():
        return make_error_response('email_exists', '该邮箱已被注册', 409)

    try:
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(email=email, password_hash=hashed_password, is_verified=False, credits=3) # 注册时即赠送3点
        db.session.add(new_user)
        db.session.commit()

        serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        token = serializer.dumps(new_user.email, salt='email-confirm-salt')
        language = data.get('language', 'en') # Get language from request, default to English

        success, detail = send_verification_email(new_user.email, token, language)
        if success:
            response_data = {'message': '注册成功! 请检查您的邮箱以激活账户。'}
            # 在开发/测试环境中，如果send_verification_email返回了URL，则将其包含在响应中
            if "http" in str(detail) or "BREVO_API_KEY not set" in str(detail):
                 # 从 "BREVO_API_KEY not set." 和打印的日志中提取URL
                verification_url_for_testing = f"http://127.0.0.1:8080/api/verify-email/{token}" if "BREVO_API_KEY not set" in str(detail) else detail
                response_data['verification_url_for_testing'] = verification_url_for_testing
            return jsonify(response_data), 201
        else:
            # 如果邮件发送失败，这依然是一个需要告知用户的情况，但不一定是服务器500错误
            return make_error_response('email_error', f'用户已创建，但验证邮件发送失败: {detail}', 502) # 502 Bad Gateway 更适合表示上游服务问题

    except Exception as e:
        db.session.rollback()
        print(f"!!! /api/register 发生严重错误: {e} !!!")
        print(traceback.format_exc())
        return make_error_response("registration_failed", f"注册过程中发生内部错误，操作已回滚。错误详情: {e}", 500)


@app.route('/api/verify-email/<token>', methods=['GET'])
def verify_email_token(token):
    # ... (代码不变)
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='email-confirm-salt', max_age=3600) # 1 hour expiration
    except SignatureExpired:
        return make_error_response('token_expired', '验证链接已过期', 400)
    except (BadTimeSignature, Exception):
        return make_error_response('token_invalid', '验证链接无效', 400)

    user = User.query.filter_by(email=email).first()
    if not user:
        return make_error_response('user_not_found', '找不到该邮箱对应的用户', 404)

    if user.is_verified:
        return redirect(url_for('verification_status', status='already_verified'))

    user.is_verified = True
    # user.credits = 3 # 激活赠送3点 - 积分已在注册时赠送
    db.session.commit()
    return redirect(url_for('verification_status', status='success'))

@app.route('/verification-status')
def verification_status():
    status = request.args.get('status')
    message = ""
    if status == 'success':
        message = "账户激活成功！已赠送3点免费创作点数。"
    elif status == 'already_verified':
        message = "账户已被激活，无需重复操作。"
    elif status == 'token_expired':
        message = "验证链接已过期。"
    elif status == 'token_invalid':
        message = "验证链接无效。"
    else:
        message = "未知验证状态。"
    
    # 这里可以返回一个简单的HTML页面，或者渲染一个模板
    # 为了简化，我们直接返回一个包含消息的HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>账户验证状态</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f0f2f5; color: #333; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; text-align: center; }}
            .container {{ background-color: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); max-width: 600px; width: 100%; }}
            h1 {{ color: #007bff; margin-bottom: 20px; }}
            p {{ font-size: 18px; line-height: 1.6; }}
            a {{ color: #007bff; text-decoration: none; font-weight: 600; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>账户验证状态</h1>
            <p>{message}</p>
            <p><a href="/">返回首页</a></p>
        </div>
    </body>
    </html>
    """
    return html_content, 200


@app.route('/api/login', methods=['POST'])
def login():
    # ... (代码不变)
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return make_error_response('missing_credentials', '请输入邮箱和密码', 401)

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return make_error_response('invalid_credentials', '邮箱或密码错误', 401)

    token = jwt.encode({'user_id': user.id, 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)},
                       app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({
        'token': token,
        'user': {
            'email': user.email,
            'credits': user.credits,
            'is_verified': user.is_verified
        }
    })


@app.route('/api/generate', methods=['POST'])
@limiter.limit("3 per day", error_message="每个IP每天只能生成3次大纲，请明天再试或注册/登录以获得更多点数。") # IP限流
@token_required
def generate_plot_outline_for_user(current_user):
    # ... (代码不变)
    is_guest = getattr(current_user, 'is_guest', False)

    if not is_guest:
        if not current_user.is_verified:
            return make_error_response('not_verified', '您的账户尚未通过邮箱验证，请先激活账户。', 403)
        if current_user.credits <= 0:
            return make_error_response('insufficient_credits', '您的创作点数不足，请充值。', 402)

    try:
        data = request.get_json()
        char1 = data.get('character1')
        char2 = data.get('character2')
        plot_prompt = data.get('plot_prompt')
        language = data.get('language', 'en') # 默认为英文

        if not all([char1, char2, plot_prompt]):
            return make_error_response('missing_input', '角色1, 角色2, 和核心梗不能为空。', 400)

        generated_text, error_info = get_ai_outline(char1, char2, plot_prompt, language)

        if error_info:
            return jsonify(error_info), 500

        remaining_credits = None
        if not is_guest:
            current_user.credits -= 1
            new_prompt_record = Prompt(user_id=current_user.id,
                                       character1_setting=char1,
                                       character2_setting=char2,
                                       core_prompt=plot_prompt,
                                       generated_outline=generated_text)
            db.session.add(new_prompt_record)
            db.session.commit()
            remaining_credits = current_user.credits

        response_data = {"outline": generated_text}
        if remaining_credits is not None:
            response_data["remaining_credits"] = remaining_credits

        return jsonify(response_data)

    except Exception as e:
        db.session.rollback() # 确保在异常发生时回滚数据库事务
        print(f"!!! /api/generate 发生未知错误: {e} !!!"); print(traceback.format_exc())
        return make_error_response("internal_server_error", "处理您的请求时发生未知错误。", 500)


@app.route('/api/outlines', methods=['POST'])
@token_required
def save_outline(current_user):
    if getattr(current_user, 'is_guest', False):
        return make_error_response("unauthorized", "游客无法保存大纲。", 403)

    data = request.get_json()
    characters = data.get('characters')
    core_scenes = data.get('core_scenes')
    outline = data.get('outline')

    if not outline:
        return make_error_response('missing_input', '大纲内容不能为空。', 400)

    try:
        new_outline = StoryOutline(
            user_id=current_user.id,
            characters=characters,
            core_scenes=core_scenes,
            outline=outline
        )
        db.session.add(new_outline)
        db.session.commit()

        return jsonify({
            "message": "大纲已成功保存。",
            "outline": {
                "id": new_outline.id,
                "created_at": new_outline.created_at.isoformat() + "Z"
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"!!! /api/outlines POST 发生错误: {e} !!!")
        print(traceback.format_exc())
        return make_error_response("internal_server_error", "保存大纲时发生内部错误。", 500)


@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user):
    if getattr(current_user, 'is_guest', False):
        return jsonify([])  # 游客没有历史记录

    history_items = []

    # 获取AI生成的历史记录
    prompts = Prompt.query.filter_by(user_id=current_user.id).all()
    for p in prompts:
        history_items.append({
            'type': 'generated', # 更简洁的类型名
            'id': p.id,
            # 将两个角色设定合并，以匹配 'characters' 的概念
            'characters': f"角色1: {p.character1_setting}\n角色2: {p.character2_setting}",
            'core_scenes': p.core_prompt, # 统一字段名
            'outline': p.generated_outline,
            'created_at': p.created_at
        })

    # 获取用户手动保存的大纲
    outlines = StoryOutline.query.filter_by(user_id=current_user.id).all()
    for o in outlines:
        history_items.append({
            'type': 'saved', # 更简洁的类型名
            'id': o.id,
            'characters': o.characters,
            'core_scenes': o.core_scenes,
            'outline': o.outline,
            'created_at': o.created_at
        })

    # 按创建时间降序排序
    history_items.sort(key=lambda x: x['created_at'], reverse=True)

    # 格式化 created_at 字段
    for item in history_items:
        item['created_at'] = item['created_at'].isoformat() + "Z"

    return jsonify(history_items)


@app.route('/api/history/<int:prompt_id>', methods=['DELETE'])
@token_required
def delete_history_item(current_user, prompt_id):
    # ... (代码不变)
    if getattr(current_user, 'is_guest', False):
        return make_error_response("unauthorized", "游客无权删除记录。", 403)

    prompt_to_delete = Prompt.query.get(prompt_id)

    if not prompt_to_delete:
        return make_error_response("not_found", "记录未找到。", 404)

    if prompt_to_delete.user_id != current_user.id:
        return make_error_response("unauthorized", "无权删除此记录。", 403)

    db.session.delete(prompt_to_delete)
    db.session.commit()
    return jsonify({"message": "记录已成功删除。"}), 200


@app.route('/api/admin/update_credits', methods=['POST'])
@admin_token_required
def admin_update_credits():
    # ... (代码不变)
    data = request.get_json()
    email = data.get('email')
    credits_to_add = data.get('credits_to_add')

    if not email or credits_to_add is None:
        return make_error_response('bad_request', '请求体中必须包含 email 和 credits_to_add', 400)

    try:
        credits_to_add = int(credits_to_add)
    except (ValueError, TypeError):
        return make_error_response('bad_request', 'credits_to_add 必须是一个整数', 400)

    user = User.query.filter_by(email=email).first()
    if not user:
        return make_error_response('user_not_found', f'找不到邮箱为 {email} 的用户', 404)

    user.credits += credits_to_add
    db.session.commit()

    print(f"管理员操作：为用户 {email} 增加了 {credits_to_add} 点数。新余额: {user.credits}")
    return jsonify({'message': '点数更新成功', 'email': user.email, 'new_credits_balance': user.credits})


# --- 5. 启动服务 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    # ✅ --- 修正拼写错误 ---
    app.run(host='0.0.0.0', port=port, debug=False)