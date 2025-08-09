# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# 「灵感方舟」后端核心应用 (Plot Ark Backend Core)
# 文件名: app.py
# 作者: Gemini (为你和Syna的梦想助力!)
# 描述: 最终胜利版！集成了多语言和增强的性别代词处理！
# 版本: 8.0 - Gender Pronoun Enhanced Version
# -----------------------------------------------------------------------------

import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# --- 1. 初始化和配置 ---
app = Flask(__name__)
load_dotenv()
CORS(app)

# --- 2. 配置Google Gemini API ---
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("API key not found. Please create a .env file and add GOOGLE_API_KEY=your_key")
genai.configure(api_key=api_key)

# --- 3. 定义API路由 ---
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

# --- 4. 启动服务器 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
