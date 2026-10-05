/**
 * AI 맞춤형 학습플래너 프론트엔드 스크립트 (app.js)
 */

document.addEventListener("DOMContentLoaded", () => {
    // -----------------------------------------------------------
    // 0. 4자리 보안 잠금 화면 (PIN Lock Overlay)
    // -----------------------------------------------------------
    const lockScreen = document.getElementById("lock-screen");
    const pinForm = document.getElementById("pin-form");
    const pinInput = document.getElementById("pin-input");
    const pinError = document.getElementById("pin-error");
    const btnLockApp = document.getElementById("btn-lock-app");

    // 세션 스토리지 잠금 상태 확인
    if (sessionStorage.getItem("app_unlocked") === "true") {
        lockScreen && lockScreen.classList.add("unlocked");
    } else if (lockScreen && !lockScreen.classList.contains("unlocked")) {
        setTimeout(() => {
            if (pinInput) pinInput.focus();
        }, 150);
    }

    // PIN 번호 제출 (서버 검증 + 애니메이션)
    if (pinForm) {
        pinForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const enteredPin = pinInput.value.trim();
            if (!enteredPin) return;

            try {
                const response = await fetch("/api/verify-pin", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ pin: enteredPin })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    if (pinError) pinError.classList.add("hidden");
                    sessionStorage.setItem("app_unlocked", "true");
                    lockScreen.classList.add("unlocked");
                    pinInput.value = "";
                } else {
                    triggerPinShake();
                }
            } catch (err) {
                console.error("PIN 검증 통신 오류:", err);
                triggerPinShake();
            }
        });
    }

    function triggerPinShake() {
        if (pinError) pinError.classList.remove("hidden");
        const card = lockScreen ? lockScreen.querySelector(".lock-card") : null;
        if (card) {
            card.classList.remove("shake");
            void card.offsetWidth; // DOM reflow 촉발
            card.classList.add("shake");
        }
        if (pinInput) {
            pinInput.value = "";
            pinInput.focus();
        }
    }

    // 상단 '🔒 잠금' 버튼 클릭 시 다시 잠금
    if (btnLockApp) {
        btnLockApp.addEventListener("click", async () => {
            sessionStorage.removeItem("app_unlocked");
            if (lockScreen) lockScreen.classList.remove("unlocked");
            if (pinError) pinError.classList.add("hidden");
            if (pinInput) {
                pinInput.value = "";
                setTimeout(() => {
                    pinInput.focus();
                }, 150);
            }
            try {
                await fetch("/logout", { method: "POST" });
            } catch (err) {
                console.error("로그아웃 오류:", err);
            }
        });
    }

    // 1. DOM 요소 가져오기
    const form = document.getElementById("plannerForm");
    const submitBtn = document.getElementById("submitBtn");
    const btnText = submitBtn.querySelector(".btn-text");

    const placeholderView = document.getElementById("placeholderView");
    const loadingView = document.getElementById("loadingView");
    const resultContent = document.getElementById("resultContent");
    const errorMessage = document.getElementById("errorMessage");
    const actionButtons = document.getElementById("actionButtons");
    const copyBtn = document.getElementById("copyBtn");
    const downloadBtn = document.getElementById("downloadBtn");

    const goalInput = document.getElementById("goal");
    const examDateInput = document.getElementById("examDate");
    const currentLevelInput = document.getElementById("currentLevel");
    const dailyTimeInput = document.getElementById("dailyTime");
    const weaknessInput = document.getElementById("weakness");
    const styleInput = document.getElementById("style");

    // 생성된 원본 마크다운 텍스트 저장용 변수
    let rawGeneratedMarkdown = "";

    // 2. 시험일 초기 기본값 설정 (오늘 기준 30일 뒤로 자동 세팅)
    const today = new Date();
    const defaultExamDate = new Date();
    defaultExamDate.setDate(today.getDate() + 30);
    const yyyy = defaultExamDate.getFullYear();
    const mm = String(defaultExamDate.getMonth() + 1).padStart(2, "0");
    const dd = String(defaultExamDate.getDate()).padStart(2, "0");
    examDateInput.value = `${yyyy}-${mm}-${dd}`;
    examDateInput.min = new Date().toISOString().split("T")[0]; // 오늘 이전 날짜 선택 방지

    // 2-1. 요일 칩 클릭 시 토글 (클릭 시 초록색 활성화, 다시 클릭 시 해제)
    const weekdayChips = document.querySelectorAll(".weekday-chip");
    weekdayChips.forEach(chip => {
        chip.addEventListener("click", () => {
            chip.classList.toggle("active");
        });
    });

    // 3. 폼 제출(Submit) 이벤트 리스너
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        // 프론트엔드 유효성 검사 (Validation)
        const goal = goalInput.value.trim();
        const examDate = examDateInput.value.trim();
        const currentLevel = currentLevelInput.value;
        const dailyTime = dailyTimeInput.value;
        const weakness = weaknessInput.value.trim();
        const style = styleInput.value;
        const promptType = form.querySelector('input[name="promptType"]:checked')?.value || "A";

        // 선택된 요일 수집
        const selectedDays = Array.from(document.querySelectorAll(".weekday-chip.active")).map(chip => chip.dataset.day);

        if (!goal || !examDate || !currentLevel || !dailyTime || !weakness || !style) {
            showError("모든 필수 입력 항목(*)을 빠짐없이 입력해주세요.");
            return;
        }

        if (selectedDays.length === 0) {
            showError("학습 가능한 요일을 최소 1개 이상 선택해주세요.");
            return;
        }

        // 상태 초기화: 로딩 중 표시
        setLoadingState(true);
        hideError();

        // 백엔드 요청 데이터 구성
        const payload = {
            goal: goal,
            exam_date: examDate,
            available_days: selectedDays,
            current_level: currentLevel,
            daily_time: dailyTime,
            weakness: weakness,
            style: style,
            prompt_type: promptType
        };

        try {
            console.log("학습플래너 생성 요청 전송:", payload);

            const response = await fetch("/generate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                if (response.status === 401) {
                    sessionStorage.removeItem("app_unlocked");
                    if (lockScreen) {
                        lockScreen.classList.remove("unlocked");
                        if (pinInput) {
                            pinInput.value = "";
                            pinInput.focus();
                        }
                    }
                }
                throw new Error(data.error || "서버에서 학습플래너를 생성하지 못했습니다.");
            }

            // 성공: 결과 화면 표시
            rawGeneratedMarkdown = data.result;
            renderMarkdown(rawGeneratedMarkdown);

        } catch (err) {
            console.error("에러 발생:", err);
            showError(err.message || "네트워크 오류 또는 서버 요청 중 문제가 발생했습니다.");
            showPlaceholder();
        } finally {
            setLoadingState(false);
        }
    });

    // 4. 마크다운 렌더링 함수
    function renderMarkdown(mdText) {
        placeholderView.style.display = "none";
        loadingView.style.display = "none";

        if (typeof marked !== "undefined" && marked.parse) {
            resultContent.innerHTML = marked.parse(mdText);
        } else {
            // fallback: 단순 텍스트 표시
            resultContent.innerHTML = `<pre>${escapeHtml(mdText)}</pre>`;
        }

        resultContent.style.display = "block";
        actionButtons.style.display = "flex";

        // 결과 영역으로 부드럽게 스크롤
        resultContent.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // 5. 로딩 상태 제어 함수
    function setLoadingState(isLoading) {
        if (isLoading) {
            submitBtn.disabled = true;
            btnText.textContent = "⏳ 플래너 설계 중 (약 10~20초)...";
            placeholderView.style.display = "none";
            resultContent.style.display = "none";
            actionButtons.style.display = "none";
            loadingView.style.display = "block";
        } else {
            submitBtn.disabled = false;
            btnText.textContent = "🚀 AI 학습플래너 생성하기";
            loadingView.style.display = "none";
        }
    }

    // 6. 플레이스홀더 표시 함수
    function showPlaceholder() {
        resultContent.style.display = "none";
        actionButtons.style.display = "none";
        placeholderView.style.display = "block";
    }

    // 7. 에러 메시지 제어 함수
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = "block";
        errorMessage.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function hideError() {
        errorMessage.style.display = "none";
        errorMessage.textContent = "";
    }

    // 8. 결과 클립보드 복사 버튼
    copyBtn.addEventListener("click", async () => {
        if (!rawGeneratedMarkdown) return;

        try {
            await navigator.clipboard.writeText(rawGeneratedMarkdown);
            const originalText = copyBtn.textContent;
            copyBtn.textContent = "✅ 복사 완료!";
            copyBtn.style.backgroundColor = "#10b981";
            copyBtn.style.color = "#ffffff";

            setTimeout(() => {
                copyBtn.textContent = originalText;
                copyBtn.style.backgroundColor = "";
                copyBtn.style.color = "";
            }, 2000);
        } catch (err) {
            alert("클립보드 복사에 실패했습니다. 수동으로 복사해주세요.");
        }
    });

    // 9. Markdown 파일 다운로드 버튼 (.md)
    downloadBtn.addEventListener("click", () => {
        if (!rawGeneratedMarkdown) return;

        const blob = new Blob([rawGeneratedMarkdown], { type: "text/markdown;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");

        const todayStr = new Date().toISOString().split("T")[0];
        const sanitizedGoal = (goalInput.value || "study_plan").replace(/[^a-zA-Z0-9가-힣_-]/g, "_");
        link.download = `학습플래너_${sanitizedGoal}_${todayStr}.md`;
        link.href = url;
        link.click();

        URL.revokeObjectURL(url);
    });

    // HTML 특수문자 이스케이프 유틸
    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }
});