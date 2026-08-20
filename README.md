# 🎨 kakao-emoticon-generator

감정 키워드(예: `기쁨`, `슬픔`, `화이팅`)를 입력하면 **볼펜 발그림 화풍**의
카카오 이모티콘 32컷을 생성하고, 카카오 이모티콘 스튜디오 제출 규격에 맞게
자동으로 후처리(배경 제거 · 리사이즈 · 투명 PNG 변환 · 품질 검사)해 주는
파이프라인입니다.

GPU나 API 키가 없어도 `sketch` 백엔드로 **지금 바로** 화풍에 맞는 그림을
뽑아볼 수 있습니다.

```bash
pip install -e .
kakao-emoticon-gen samples --mode lineup --count 7 --out lineup.png
```

동물형 7종(곰 · 햄스터 · 토끼 · 고양이 · 강아지 · 오리 · 물범)을 지원하며,
종마다 귀 · 코 · 주둥이 · 볼주머니 · 수염 · 앞니 조합이 다릅니다.
움직이는 이모티콘(GIF)도 `animate` 명령으로 뽑을 수 있습니다.

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
| GPU/API 없이 **실제 발그림 스타일 그림**이 필요 | `sketch` | 없음 (Pillow만으로 절차적 렌더링) |
| 파이프라인 배관만 확인 | `mock` | 없음 (단순 플레이스홀더) |
| GPU 없음 / API 비용 지불 가능 | `dalle` (OpenAI Images API) | `OPENAI_API_KEY`, 인터넷 |
| GPU 있음(8GB+ VRAM) / 무료로 대량 생성 | `stable_diffusion` (로컬 diffusers) | `torch`, `diffusers`, GPU |

이모티콘 스타일은 `src/kakao_emoticon_gen/prompts.py`의 `STYLE_PRESETS`에서 고릅니다.
기본값은 **`pen_doodle` (볼펜 발그림)** 입니다.

| 프리셋 | 설명 |
| --- | --- |
| `pen_doodle` **(기본값)** | 얇고 떨리는 볼펜 선 · 검정 짝눈 · 좌우 비대칭 · 선 밖으로 삐져나간 채색 |
| `text_based` | 하단에 손글씨 문구를 얹을 빈 공간을 확보 (한글은 AI가 아닌 후처리에서) |
| `animated_frame` | 움직이는 GIF용 단일 프레임 |
| `cute_character` | 발그림 화풍을 쓰지 않을 때의 깔끔한 대안 |

> 📖 **볼펜 발그림 화풍의 고정 규칙(눈·선·비율·채색), 캐릭터 일관성 유지법,
> AI 티 제거 후처리, 제출 전 체크리스트는 [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md)에
> 정리돼 있습니다. 32컷 작업을 시작하기 전에 먼저 읽어주세요.**

GIF(움직이는) 이모티콘은 `sketch` 백엔드에서 `animate` 명령으로 바로 뽑을 수
있습니다(`bounce`/`wiggle`/`nod`). AI 백엔드를 쓸 땐 `animated_frame` 프리셋으로
프레임을 뽑아 `postprocess.frames_to_gif`로 합칩니다.

### ⚠️ 한글 텍스트는 AI에 시키지 마세요

이미지 생성 AI는 한글을 거의 항상 깨뜨립니다. **그림만 뽑고**, 텍스트는
프로크리에이트/포토샵/클립스튜디오에서 손글씨 폰트로 직접 얹으세요
(**흰색 아웃라인 필수** — 다크모드 대응). 모든 프리셋의 네거티브 프롬프트가
`korean text`, `hangul`, `letters`를 차단하도록 구성돼 있습니다.

---

## 1. 전체 구조

```
kakao-emoticon-generator/
├── docs/STYLE_GUIDE.md     # 볼펜 발그림 화풍 고정 규칙 + 제출 체크리스트
├── src/kakao_emoticon_gen/
│   ├── sketchgen.py        # 발그림 캐릭터 절차적 렌더러 (AI 불필요)
│   ├── config.py           # 환경변수(.env) 로딩
│   ├── prompts.py          # 감정 키워드 → 카카오 이모티콘 스타일 프롬프트 (32컷 세트)
│   ├── copyright_guard.py  # 저작권/브랜드명 + 참고 작가명 금칙어 필터
│   ├── backends/
│   │   ├── base.py             # ImageGenerator 추상 인터페이스
│   │   ├── sketch.py           # 절차적 발그림 렌더러 어댑터
│   │   ├── mock.py             # 파이프라인 배관 확인용 플레이스홀더
│   │   ├── stable_diffusion.py # 로컬 Stable Diffusion (diffusers)
│   │   └── dalle.py            # OpenAI Images API
│   ├── postprocess.py      # 배경 제거, 손떨림 지터(AI 티 제거), 360x360 리사이즈, GIF
│   ├── quality.py          # 품질 필터 (블러/빈 이미지/투명도/다크모드 가독성)
│   ├── kakao_spec.py       # 제출 규격 검증 (PNG/360x360/투명배경/용량/32컷)
│   ├── pipeline.py         # 전체 오케스트레이션
│   └── cli.py               # CLI 진입점
├── tests/                  # pytest 유닛 테스트 (GPU/API 불필요)
├── examples/emotion_set.yaml
├── output/                 # 생성 결과 (approved / needs_review 로 자동 분류)
├── pyproject.toml          # 패키지 정의 + kakao-emoticon-gen 콘솔 스크립트
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
[backends/*]         이미지 생성 (sketch / mock / dalle / stable_diffusion)
   │
   ▼
[postprocess.py]     배경 제거 → 손떨림 지터(AI 티 제거) → 정사각 패딩
                     → 360x360 리사이즈 → RGBA PNG
   │
   ▼
[quality.py]         품질 필터 (빈 이미지, 블러, 투명도 비율, 다크모드 가독성)
   │              ├─ 실패 → output/needs_review/ (사람 검수 대기)
   │              └─ 통과
   ▼
[kakao_spec.py]      카카오 제출 규격 검증 (형식/해상도/투명배경/파일 용량)
   │              ├─ 실패 → output/needs_review/
   │              └─ 통과 → output/approved/ + manifest.json 기록
   ▼
   사람이 직접 검수 (`cli.py checklist` — 화풍 통일감·실루엣·논버벌 테스트)
```

---

## 2. 설치

```bash
git clone https://github.com/alswn8268/kakao-emoticon-generator.git
cd kakao-emoticon-generator

python3 -m venv .venv && source .venv/bin/activate
pip install -e .        # 최소 의존성(Pillow, numpy) + kakao-emoticon-gen 명령 등록

# 선택 사항 (사용할 백엔드에 맞게 설치)
pip install -e ".[dalle]"   # OpenAI Images API 백엔드
pip install -e ".[sd]"      # 로컬 Stable Diffusion 백엔드
pip install -e ".[rembg]"   # 고품질 배경 제거 (없으면 간이 알고리즘으로 대체)
pip install -e ".[dev]"     # pytest

cp .env.example .env   # 필요한 값 채우기
```

설치하면 아래 두 가지가 모두 동작합니다.

```bash
kakao-emoticon-gen checklist              # 콘솔 스크립트
python -m kakao_emoticon_gen.cli checklist # 모듈 실행
```

---

## 3. 사용법

```bash
# 0) 동물 캐릭터 후보 7종을 같은 표정으로 뽑아 디자인 비교
python -m kakao_emoticon_gen.cli samples --mode lineup --count 7 --out output/lineup.png

# 0-1) 마음에 드는 후보의 seed로 32컷 표정 세트 전체를 미리보기
python -m kakao_emoticon_gen.cli samples --mode expressions \
    --character-seed 5 --cols 8 --cell 200 --out output/set.png

# 0-2) 다크모드 배경에서 묻히지 않는지 눈으로 확인
python -m kakao_emoticon_gen.cli samples --mode expressions \
    --character-seed 5 --dark --out output/set_dark.png

# 0-3) 움직이는 이모티콘(GIF) 뽑기
python -m kakao_emoticon_gen.cli animate --keyword 기쁨 --motion bounce \
    --animal hamster --character-seed 4 --out output/bounce.gif

# 1) GPU/API 없이 실제 발그림 그림으로 32컷 생성 (세트 크기 일정하게)
python -m kakao_emoticon_gen.cli generate \
    --emotions "기쁨,슬픔,화남,사랑해,화이팅" \
    --backend sketch --character-seed 5 --fit canvas --seed 11 --jitter 0.8 \
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

# 4) 32컷 전체 세트를 한 번에 (참고 감정 세트 그대로 사용)
python -m kakao_emoticon_gen.cli generate \
    --emotions "$(python -c 'from kakao_emoticon_gen import prompts; print(",".join(prompts.RECOMMENDED_EMOTION_SET))')" \
    --backend mock --seed 100 --out output/

# 규격 + 32컷 장수까지 세트 단위로 검증
python -m kakao_emoticon_gen.cli validate --path output/approved

# 제출 전 수동 검토 체크리스트 출력
python -m kakao_emoticon_gen.cli checklist

# 참고 감정 세트(32컷)와 스타일 프리셋 목록 확인
python -m kakao_emoticon_gen.cli list-emotions
```

주요 옵션:

| 옵션 | 설명 |
| --- | --- |
| `--style` | 스타일 프리셋 (기본 `pen_doodle`) |
| `--seed` | 컷마다 `seed + i`로 파생돼 톤이 안정됩니다. 재현에도 필요 |
| `--jitter` | AI 티 제거용 손떨림 강도(픽셀, 기본 1.5). `0`이면 끕니다 |
| `--fit` | `canvas`는 원본 프레이밍을 유지해 **세트 내 캐릭터 크기를 일정하게** 합니다. 기본값 `content`는 컷마다 내용물에 꽉 차게 확대하므로, 팔을 벌린 컷의 몸통이 작아져 32컷 통일감이 깨집니다 |
| `--character-seed` | `sketch` 백엔드의 캐릭터 디자인. **세트 내내 같은 값**을 써야 같은 캐릭터가 됩니다 |
| `--animal` | 동물 종류를 직접 고릅니다 (`bear`/`hamster`/`rabbit`/`cat`/`dog`/`duck`/`seal`) |

결과물:

- `output/approved/*.png` — 카카오 제출 규격(PNG, 360×360, 투명 배경) 통과 + 품질 필터 통과
- `output/needs_review/*.png` — 규격 또는 품질 필터에 걸려 **사람이 직접 확인**해야 하는 이미지
- `output/manifest.json` — 각 이미지의 프롬프트, 검증 결과, 통과 여부 기록

> `approved`는 **규격 통과**를 뜻할 뿐 "제출해도 좋다"는 뜻이 아닙니다.
> 화풍 통일감·실루엣 유사성·논버벌 전달력은 자동 검사가 판단할 수 없으므로,
> `checklist`를 돌려 반드시 사람이 눈으로 확인하세요.

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
| 파일 용량 | 150KB 이하 |
| 세트 장수 | 32컷 (디렉터리 단위 `validate` 시 검사) |

> 카카오의 정식 제출 규격(시안 3종, 정식 24종+상세이미지 등)은 카카오
> 이모티콘 스튜디오 공지에 따라 바뀔 수 있으므로, **제출 직전 반드시
> [카카오 이모티콘 스튜디오](https://emoticonstudio.kakao.com) 공식 가이드로
> 최신 규격을 재확인**하세요. 이 도구는 가장 핵심적인 공통 규격(PNG,
> 360×360, 투명 배경)만 강제하는 안전장치입니다.

---

## 5. 저작권 관련 안전장치

1. `copyright_guard.py`의 `BLOCKLIST`에 유명 캐릭터/브랜드명을 등록해두면,
   프롬프트에 해당 단어가 포함될 경우 **생성 전에 차단**하고 경고를 띄웁니다.
2. `STYLE_REFERENCE_BLOCKLIST`는 **화풍 참고 대상의 작가/캐릭터 이름**을
   따로 차단합니다. 이름을 프롬프트에 넣으면 화풍만이 아니라 실루엣까지
   따라가 심사 탈락 사유가 되기 때문입니다. **화풍은 이름이 아니라
   서술(선·눈·비율·채색)로만 재현**하세요 — `pen_doodle` 프리셋이 그 방식입니다.
3. 모든 생성 요청에 `"original character, not based on any existing
   copyrighted character or brand"` 문구와 네거티브 프롬프트가 자동으로
   추가됩니다.
4. 그럼에도 AI 모델은 학습 데이터의 영향으로 기존 캐릭터와 유사한 결과를
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
- `check_dark_mode_legibility`: 검은 볼펜 선만 있고 밝은 채색이 거의 없어
  **다크모드 채팅 배경에서 형체가 묻히는** 컷을 감지

> ⚠️ 이 필터들은 **화풍의 완성도를 판단하지 못합니다.** "선이 너무 깔끔한지",
> "32컷의 낙서 텐션이 일정한지"는 사람만 판별할 수 있습니다
> (→ [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) 체크리스트).

---

## 7. 테스트

```bash
pip install -e ".[dev]"
pytest -v
```

모든 테스트는 `mock`/`sketch` 백엔드와 Pillow·numpy만으로 동작하며
GPU나 API 키가 필요 없습니다.
