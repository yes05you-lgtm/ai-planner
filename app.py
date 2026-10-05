import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
import google.generativeai as genai

# 1. 로깅 설정 (Backend Log)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# 2. 환경변수(.env) 로드
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "study-planner-secret-key-2026")
ACCESS_PIN = os.getenv("ACCESS_PIN", "1234")  # 기본 4자리 비밀번호 (1234)
PORT = int(os.getenv("PORT", 5000))

# 3. Gemini API 초기화
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)
    logging.info("Gemini API가 성공적으로 설정되었습니다.")
else:
    logging.warning("유효한 GEMINI_API_KEY가 .env 파일에 설정되지 않았습니다.")

# 4. Flask 앱 초기화 (Vercel 및 로컬 환경 모두 호환되도록 절대 경로 지정)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
app.secret_key = FLASK_SECRET_KEY


@app.route("/api/verify-pin", methods=["POST"])
def verify_pin():
    """4자리 PIN 비밀번호 검증 API (오버레이 잠금 화면용)"""
    data = request.get_json() or {}
    input_pin = str(data.get("pin", "")).strip()
    if input_pin == ACCESS_PIN:
        session["authenticated"] = True
        logging.info("비밀번호 4자리 인증 성공")
        return jsonify({"success": True})
    else:
        logging.warning("비밀번호 인증 실패: 잘못된 PIN 입력")
        return jsonify({"success": False, "error": "비밀번호가 올바르지 않습니다."}), 401


@app.route("/login", methods=["GET", "POST"])
def login():
    """기존 로그인 페이지 접근 시 메인 화면으로 리다이렉트 (메인 화면에서 오버레이 락 작동)"""
    return redirect(url_for("index"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    """로그아웃 / 잠금 처리"""
    session.pop("authenticated", None)
    logging.info("사용자 잠금/로그아웃 완료")
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True})
    return redirect(url_for("index"))


@app.route("/")
@app.route("/app")
@app.route("/app.py")
@app.route("/api/index")
@app.route("/api/index.py")
def index():
    """메인 페이지 렌더링 (다양한 진입 경로 / 및 /app 지원)"""
    is_auth = session.get("authenticated", False)
    logging.info(f"[GET {request.path}] 메인 페이지 접근 (인증 여부: {is_auth})")
    return render_template("index.html", is_authenticated=is_auth)


@app.errorhandler(404)
def handle_not_found(e):
    """Vercel 리라이트 경로 차이나 URL 오타로 404 발생 시 메인 페이지로 부드럽게 안내"""
    if request.method == "GET" and not request.path.startswith("/static/"):
        logging.info(f"[404 Fallback] {request.path} -> 메인 페이지로 복구 렌더링")
        return render_template("index.html", is_authenticated=session.get("authenticated", False))
    return jsonify({"error": "요청하신 리소스를 찾을 수 없습니다."}), 404


@app.route("/generate", methods=["POST"])
def generate_study_plan():
    """AI 학습플래너 생성 API (인증 필수)"""
    if not session.get("authenticated"):
        logging.warning("[401] 비인가 요청: 세션 인증 만료")
        return jsonify({"success": False, "error": "로그인 세션이 만료되었습니다. 새로고침 후 다시 로그인해주세요."}), 401

    logging.info("[POST /generate] 학습플래너 생성 요청 접수")

    try:
        # 클라이언트 요청 데이터 파싱
        data = request.get_json()
        if not data:
            logging.warning("[400] 요청 본문(JSON)이 비어있습니다.")
            return jsonify({"success": False, "error": "요청 데이터가 올바르지 않습니다."}), 400

        # 입력 데이터 추출
        goal = data.get("goal", "").strip()
        exam_date = data.get("exam_date", "").strip()
        available_days = data.get("available_days", [])
        current_level = data.get("current_level", "").strip()
        daily_time = data.get("daily_time", "").strip()
        weakness = data.get("weakness", "").strip()
        style = data.get("style", "").strip()
        prompt_type = data.get("prompt_type", "A").strip()

        # 백엔드 입력값 검증 (Validation)
        missing_fields = []
        if not goal:
            missing_fields.append("학습목표")
        if not exam_date:
            missing_fields.append("시험일")
        if not available_days:
            missing_fields.append("학습 가능한 요일")
        if not current_level:
            missing_fields.append("현재 수준")
        if not daily_time:
            missing_fields.append("하루 가능시간")
        if not weakness:
            missing_fields.append("취약영역")
        if not style:
            missing_fields.append("선호 학습방식")

        if missing_fields:
            error_msg = f"다음 필수 입력 항목이 누락되었습니다: {', '.join(missing_fields)}"
            logging.warning(f"[400] 필수 항목 누락: {error_msg}")
            return jsonify({"success": False, "error": error_msg}), 400

        # API 키 검증
        current_api_key = os.getenv("GEMINI_API_KEY")
        if not current_api_key or current_api_key == "your_gemini_api_key_here":
            error_msg = ".env 파일에 유효한 GEMINI_API_KEY가 설정되지 않았습니다. API 키를 입력해주세요."
            logging.error(f"[500] {error_msg}")
            return jsonify({"success": False, "error": error_msg}), 500

        # Gemini API 다시 설정(실시간 반영 보장)
        genai.configure(api_key=current_api_key)

        # 프롬프트 모드별 페르소나 및 지침 정의
        if prompt_type == "B":
            role_guide = """
[모드: B. 전문가 집중 트레이닝 모드]
- 냉철하고 효율성을 극대화하는 수험/학습 전략 컨설턴트 톤앤매너
- 취약영역을 단기간에 극복하기 위한 집중 드릴 및 약점 제거 위주의 전략 제시
- 시간 낭비를 최소화하고 실전 시험에서 점수를 끌어올리는 압축 고효율 플랜
"""
        else:
            role_guide = """
[모드: A. 맞춤형 친절 페이스메이커 모드]
- 수험생의 멘탈 관리와 지속 가능한 습관 형성을 돕는 다정하고 격려하는 멘토 톤앤매너
- 무리하지 않고 시험일까지 완주할 수 있는 균형 잡힌 점진적 플랜 제시
"""

        # 마스터 프롬프트 구성
        today_str = datetime.now().strftime("%Y-%m-%d")
        system_prompt = f"""
당신은 대한민국 최고의 수험/학습 전략 컨설턴트이자 에듀테크 AI 플래너입니다.
수험생의 조건과 입력을 바탕으로 실천 가능하고 체계적인 '맞춤형 AI 학습플래너'를 Markdown 형식으로 작성해주세요.

{role_guide}

[수험생 입력 정보]
- 작성 기준일: {today_str}
- 학습 목표: {goal}
- 시험일(목표일): {exam_date}
- 학습 가능한 요일: {', '.join(available_days)}
- 현재 수준: {current_level}
- 하루 가능 시간: {daily_time}
- 취약 영역: {weakness}
- 선호 학습 방식: {style}
- 주의사항: 주간 및 일일 계획 수립 시, 반드시 수험생이 선택한 학습 가능한 요일({', '.join(available_days)}) 위주로 필수 학습을 편성하고, 선택하지 않은 요일은 휴식 또는 자율 보충일로 배치하세요.

[반드시 포함해야 할 6대 핵심 출력 구조]
다음 6개 섹션을 빠짐없이 Markdown 대제목(##)과 소제목(###), 표(Table), 체크리스트(-)를 사용하여 명확하게 작성하세요:

## 1. 📅 주간 계획 (Weekly Roadmap)
- 기준일부터 시험일까지의 주차별 핵심 마일스톤 및 주간 학습 목표를 표 형태로 제공

## 2. ⏰ 일일 계획 및 타임테이블 (Daily Routine)
- 하루 가용 시간({daily_time})에 맞춘 구체적인 시간대별(오전/오후/저녁/자투리) 분 단위 실행 루틴
- 개념 학습, 문제 풀이, 오답 정리의 적정 비율 배분

## 3. 🔄 에빙하우스 망각곡선 기반 복습주기 (Review Cycle)
- 당일 복습(1일 후), 주간 복습(3일/7일 후), 누적 복습(14일/30일 후) 주기 안내
- 취약 영역({weakness})을 집중 재복습하기 위한 구체적인 복습 기법 제시

## 4. ❓ 실전 자가 점검문항 (Self-Check Quiz)
- 현재 수준({current_level})과 취약 영역({weakness})을 점검할 수 있는 핵심 질문/점검 퀴즈 3~5문항 제시 (정답 또는 채점 기준 힌트 포함)

## 5. ✅ 진도 체크리스트 (Progress Checklist)
- 수험생이 직접 체크박스로 완료 여부를 표시할 수 있는 형식 (`- [ ]`)의 체크리스트 제공

## 6. 📝 일일 & 주간 학습 회고 템플릿 (Retrospective Framework)
- KPT(Keep, Problem, Try) 또는 4F 기반의 학습 회고 서식
- 수험생을 위한 맞춤형 격려 및 응원 한마디

[작성 가이드]
- 가독성이 높도록 볼드체, 인용구, 이모지, 글머리 기호, 표를 적절히 활용하세요.
- 비현실적인 무리한 분량은 지양하고, 실제 실천할 수 있는 현실적인 플랜으로 제안하세요.
"""

        logging.info(f"Gemini API 호출 시작 (모드: {prompt_type}, 목표: {goal})")

        # 초고속 및 넉넉한 쿼터의 gemini-3.5-flash-lite 모델 호출
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        response = model.generate_content(system_prompt)

        generated_text = response.text if response and hasattr(response, "text") else ""

        if not generated_text:
            raise ValueError("Gemini API로부터 생성된 결과 내용이 없습니다.")

        logging.info(f"학습플래너 생성 성공! 응답 글자수: {len(generated_text)}자")

        return jsonify({
            "success": True,
            "result": generated_text,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        error_detail = str(e)
        logging.error(f"[500] 학습플래너 생성 중 오류 발생: {error_detail}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"AI 플래너 생성 중 오류가 발생했습니다: {error_detail}"
        }), 500


if __name__ == "__main__":
    logging.info(f"AI 학습플래너 Flask 서버 시작 (포트: {PORT})")
    app.run(host="127.0.0.1", port=PORT, debug=True)