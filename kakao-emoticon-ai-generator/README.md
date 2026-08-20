# 🎨 카카오 이모티콘 AI 생성기 (Kakao Emoticon AI Generator)

감정 키워드(예: `기쁨`, `슬픔`, `화이팅`)를 입력하면 카카오 이모티콘 스타일의
캐릭터 이미지를 AI로 생성하고, 카카오 이모티콘 스튜디오 제출 규격에 맞게
자동으로 후처리(배경 제거 · 리사이즈 · 투명 PNG 변환 · 품질 검사)해 주는
파이프라인입니다.

> ⚠️ **면책 조항**: 이 도구는 제작 과정을 자동화/보조할 뿐입니다.
> 최종 이미지는 반드시 **사람이 직접 검수**하고, 기존 캐릭터·브랜드와
> 유사성이 없는지 확인한 뒤 제출하세요. 저작권 침해 여부에 대한 최종
> 책임은 제출자(사용자)에게 있습니다.

---

## 0. 먼저 확인해야 할 것 (Calibration)

이 파이프라인은 사용자의 환경에 따라 세 가지 백엔드 중 하나를 선택합니다.
아래 표를 보고 본인 환경에 맞는 백엔드를 `.env`에 설정하세요.

| 상황 | 추천 백엔드 | 필요한 것 |
| --- | --- | --- |
| GPU 없음 / 우선 파이프라인만 테스트 | `mock` | 없음 (Pillow만 있으면 즉시 동작, 플레이스홀더 이미지 생성) |
| GPU 없음 / API 비용 지불 가능 | `dalle` (OpenAI Images API) | `OPENAI_API_KEY`, 인터넷 |
| GPU 있음(8GB+ VRAM) / 무료로 대량 생성 | `stable_diffusion` (로컬 diffusers) | `torch`, `diffusers`, GPU |

이모티콘 스타일(귀여운 캐릭터형 / 텍스트형 / 움직이는 GIF형)은
`src/kakao_emoticon_gen/prompts.py`의 `STYLE_PRESETS`에서 고릅니다.
기본값은 **귀여운 캐릭터형(정지 이미지)** 입니다. GIF(움직이는) 이모티콘은
이 저장소에서 프레임 단위 정지 이미지 생성까지만 자동화하며, 프레임 보간·
GIF 인코딩은 `postprocess.py`의 `frames_to_gif`로 별도 지원합니다.

---

## 1. 전체 구조

```
kakao-emoticon-ai-generator/
├── src/kakao_emoticon_gen/
│   ├── config.py           # 환경변수(.env) 로딩
│   ├── prompts.py          # 감정 키워드 → 카카오 이모티콘 스타일 프롬프트
│   ├── copyright_guard.py  # 저작권/브랜드명 금칙어 필터 + 네거티브 프롬프트 강제
│   ├── backends/
│   │   ├── base.py             # ImageGenerator 추상 인터페이스
│   │   ├── mock.py             # GPU/API 없이 테스트용 플레이스홀더 생성기
│   │   ├── stable_diffusion.py # 로컬 Stable Diffusion (diffusers)
│   │   └── dalle.py            # OpenAI Images API
│   ├── postprocess.py      # 배경 제거, 360x360 리사이즈, 투명 PNG 저장, GIF 인코딩
│   ├── quality.py          # 품질 필터 (블러/빈 이미지/투명도 비율 검사)
│   ├── kakao_spec.py       # 카카오 제출 규격 검증 (PNG/360x360/투명배경/용량)
│   ├── pipeline.py         # 전체 오케스트레이션
│   └── cli.py               # CLI 진입점
├── tests/                  # pytest 유닛 테스트 (mock 백엔드만 사용, GPU/API 불필요)
├── examples/emotion_set.yaml
├── output/                 # 생성 결과 (approved / needs_review 로 자동 분류)
├── requirements.txt
└── .env.example
```

### 파이프라인 흐름

```
키워드 입력
   │
   ▼
[prompts.py]        감정 키워드 → 카카오 스타일 프롬프트 템플릿 결합
   │
   ▼
[copyright_guard.py]  브랜드/캐릭터 금칙어 검사 + 네거티브 프롬프트 강제 삽입
   │
   ▼
[backends/*]         이미지 생성 (mock / dalle / stable_diffusion)
   │
   ▼
[postprocess.py]     배경 제거 → 정사각 캔버스 패딩 → 360x360 리사이즈 → RGBA PNG
   │
   ▼
[quality.py]         품질 필터 (빈 이미지, 과도한 블러, 비정상 투명도 비율)
   │              ├─ 실패 → output/needs_review/ (사람 검수 대기)
   │              └─ 통과
   ▼
[kakao_spec.py]      카카오 제출 규격 검증 (형식/해상도/투명배경/파일 용량)
   │              ├─ 실패 → output/needs_review/
   │              └─ 통과 → output/approved/ + manifest.json 기록
```

---

## 2. 설치

```bash
cd kakao-emoticon-ai-generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # 최소 의존성 (Pillow, numpy 등)

# 선택 사항 (사용할 백엔드에 맞게 설치)
pip install openai                     # DALL·E 백엔드
pip install torch diffusers accelerate # 로컬 Stable Diffusion 백엔드
pip install rembg                      # 고품질 배경 제거 (없으면 간이 알고리즘으로 대체)

cp .env.example .env   # 필요한 값 채우기
```

---

## 3. 사용법

```bash
# 1) 백엔드 없이 파이프라인부터 검증 (플레이스홀더 이미지)
python -m kakao_emoticon_gen.cli generate \
    --emotions "기쁨,슬픔,화남,사랑해,화이팅" \
    --backend mock \
    --out output/

# 2) OpenAI DALL·E로 실제 생성
export OPENAI_API_KEY=sk-...
python -m kakao_emoticon_gen.cli generate \
    --emotions "기쁨,슬픔,화남" \
    --backend dalle \
    --out output/

# 3) 로컬 Stable Diffusion (GPU 필요)
python -m kakao_emoticon_gen.cli generate \
    --emotions "기쁨,슬픔,화남" \
    --backend stable_diffusion \
    --model runwayml/stable-diffusion-v1-5 \
    --out output/

# 이미 생성된 이미지가 카카오 규격에 맞는지만 검증
python -m kakao_emoticon_gen.cli validate --path output/approved
```

결과물:

- `output/approved/*.png` — 카카오 제출 규격(PNG, 360×360, 투명 배경) 통과 + 품질 필터 통과
- `output/needs_review/*.png` — 규격 또는 품질 필터에 걸려 **사람이 직접 확인**해야 하는 이미지
- `output/manifest.json` — 각 이미지의 프롬프트, 검증 결과, 통과 여부 기록

---

## 4. 카카오 제출 규격 (구현 기준)

`kakao_spec.py`는 카카오 이모티콘 스튜디오의 **제안(시안) 단계** 정지 이미지
기준으로 다음을 검증합니다. (움직이는 이모티콘/큰 이모티콘 등은 규격이 다르며,
`SUBMISSION_PROFILES`에 프로필을 추가해 확장할 수 있습니다.)

| 항목 | 기준 |
| --- | --- |
| 포맷 | PNG |
| 해상도 | 360 × 360 px |
| 배경 | 투명 (알파 채널 존재 + 실제로 투명 픽셀 포함) |
| 색상 모드 | RGBA |
| 파일 용량 | 150KB 이하 (기본값, `--max-kb`로 조정 가능) |

> 카카오의 정식 제출 규격(시안 3종, 정식 24종+상세이미지 등)은 카카오
> 이모티콘 스튜디오 공지에 따라 바뀔 수 있으므로, **제출 직전 반드시
> [카카오 이모티콘 스튜디오](https://emoticonstudio.kakao.com) 공식 가이드로
> 최신 규격을 재확인**하세요. 이 도구는 가장 핵심적인 공통 규격(PNG,
> 360×360, 투명 배경)만 강제하는 안전장치입니다.

---

## 5. 저작권 관련 안전장치

1. `copyright_guard.py`의 `BLOCKLIST`에 유명 캐릭터/브랜드명을 등록해두면,
   프롬프트에 해당 단어가 포함될 경우 **생성 전에 차단**하고 경고를 띄웁니다.
2. 모든 생성 요청에 `"original character, not based on any existing
   copyrighted character or brand"` 문구와 네거티브 프롬프트가 자동으로
   추가됩니다.
3. 그럼에도 AI 모델은 학습 데이터의 영향으로 기존 캐릭터와 유사한 결과를
   낼 수 있습니다. **`needs_review` 검수 단계에서 사람이 반드시 육안으로
   기존 IP와의 유사성을 확인**하세요. 이 저장소는 이미지 유사도 기반의
   저작권 자동 판별 기능은 제공하지 않습니다 (오탐/미탐 위험이 크기 때문).

---

## 6. 품질 필터 (`quality.py`)

자동 생성 결과의 품질 편차를 줄이기 위한 최소한의 휴리스틱 필터입니다.
완벽한 품질 보증은 아니며, **탈락시키는 것보다 사람 검수로 넘기는 것**을
기본 전략으로 합니다.

- `check_not_blank`: 단색/빈 이미지 여부
- `check_blur`: 에지 검출 기반 블러 정도 추정
- `check_transparency_ratio`: 배경 제거가 과도하거나(캐릭터까지 날아감)
  전혀 되지 않은 경우 감지

---

## 7. 테스트

```bash
pip install pytest
pytest tests/ -v
```

모든 테스트는 `mock` 백엔드와 Pillow만으로 동작하며 GPU/API 키가 필요 없습니다.
