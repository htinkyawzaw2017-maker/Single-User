# 🇲🇲 အသုံးပြုပုံ လမ်းညွှန် (မြန်မာ)

ဤ document တွင် **Single-User Burmese/English Movie Dubbing Tool** ကို
စတင်အသုံးပြုပုံမှ အဆုံး export ထုတ်ပုံအထိ အသေးစိတ်ရှင်းပြထားပါတယ်။

---

## ၁။ အစပြုခြင်း (Local မှာ စမ်းသပ်ခြင်း)

### အရင်ဆုံး လိုအပ်ချက်များ

- Python 3.11 (သို့မဟုတ် အထက်)
- Node.js 20+ (npm ပါဝင်)
- ffmpeg — မရှိရင်ပဲ ရပါတယ်၊ `imageio-ffmpeg` package က static ffmpeg
  ကို auto ယူပေးပါလိမ့်မယ်

### စတင်အလုပ်လုပ်ခြင်း

```bash
# backend ကို ပြင်ဆင်ခြင်း
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# frontend ကို build ခြင်း
cd ../frontend
npm install
npm run build

# server ကို ဖွင့်ခြင်း (backend + frontend နှစ်ခုလုံး တစ်ပြိုင်တည်း)
cd ../backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Browser မှာ `http://localhost:8000` ကို ဖွင့်ပါ။

> **Development mode** (hot-reload လိုချင်ရင်) — `./scripts/dev.sh`
> ကို run ပါ။ Frontend :5173၊ Backend :8000 နှစ်ခုလုံး ဖွင့်ပေးမယ်။

### Access Key ခတ်ခြင်း (optional)

တစ်ယောက်တည်းသုံးတဲ့ private tool ဖြစ်လို့ ရိုးရိုးလည်း ရပါတယ်။
ပိုတိုးတွက်ချင်ရင် —

```bash
SINGLE_USER_ACCESS_KEY="ငါ့-လျှို့ဝှက်-စကားလုံး" .venv/bin/python -m uvicorn ...
```

ခတ်ထားရင် app ဖွင့်တဲ့အခါ key ထည့်ခိုင်းမယ်။ Browser ရဲ့ localStorage
မှာ သိမ်းထားပြီး နောက်တစ်ခေါက် ထပ်မထည့်နေရပါဘူး။

---

## ၂။ Mock Providers အကြောင်း

Default အနေနဲ့ app က **အင်တာနက်လိုင်း မလိုဘဲ** အလုပ်လုပ်အောင်
mock providers နဲ့ စတင်ထားပါတယ် —

| အပိုင်း | Mock လုပ်ဆောင်ချက် | အစားထိုးရန် |
|---|---|---|
| Transcription | ffmpeg silencedetect နဲ့ အသံအတိုအရှည်ကို ကြည့်ပြီး timestamp ထုတ်ပေး (စာသားက placeholder) | `TRANSCRIPTION_PROVIDER=aws` (Amazon Transcribe) |
| Translation | EN⇄MY အခြေခံ အလယ်အလတ်စာလုံး စာရင်းနဲ့ ပြန်ဆိုပေး | `TRANSLATION_PROVIDER=llm` + `LLM_BASE_URL/LLM_API_KEY` |
| TTS | voice တစ်ခုစီအတွက် ကွဲပြားတဲ့ tone သံထုတ်ပေး (အရှည်က စာသားအရ ခန့်မှန်း) | `TTS_PROVIDER=http` + `TTS_HTTP_URL` |
| Lip-sync | preview clip ကို တကယ်ထုတ်ပေးပေမယ့် ပါးစပ်လှုပ်ရုံက mock | `LIPSYNC_PROVIDER=sagemaker` |

Mock သုံးနေစဉ်မှာလည်း **pipeline တစ်ခုလုံး စစ်မှန်စွာ အလုပ်လုပ်ပါတယ်** —
upload → transcribe → translate → စာပြင် → အသံထုတ် → timing ညှိ →
mix → export MP4/SRT အထိ။ စာသားတွေကို မင်းက review လုပ်ပြီးမှ
အသံထုတ်တာမို့ mock output ကိုလည်း ဘေးဖယ်ပြီး သုံးလို့ရပါတယ်။

Real provider ချိတ်ပုံကို အောက်ပါ အပိုင်း (၈) မှာ အသေးစိတ် ရှင်းပြထားပါတယ်။

---

## ၃။ Project ဖန်တီးခြင်း

1. **Dashboard** (ပထမစာမျက်နှာ) → **Create new project** ကို နှိပ်ပါ။
2. ဖောင်ထဲမှာ ဖြည့်ပါ —
   - **Project name** — နာမည်ပေးပါ
   - **Source language** — မူရင်း ဇာတ်ကြောင်းသုံးဘာသာ (English သို့ မြန်မာ)
   - **Target language** — dub ထုတ်မယ့်ဘာသာ (တစ်ခုနဲ့တစ်ခု မတူရ)
   - **Mode** —
     - `Recap narration` — scene တစ်ခုချင်းစာ narration သွားမယ်၊ lip-sync မပါ
     - `Dialogue dubbing` — စကားပိုဒ်ချင်း dub လုပ်မယ် (default)
     - `Dialogue dubbing + lip-sync` — dub + ရွေးချယ်နိုင်တဲ့ lip-sync (beta)
   - **Voice style** — natural / dramatic / calm / energetic
   - **Instructions for AI rewrite** — ဘာသာပြန်ရာမှာ လိုက်နာစေချင်တဲ့
     ညွှန်ကြားချက်များ (ဥပမာ - "အရေးပြော မြန်မာသုံးပါ၊ ဇာတ်ကောင်နာမည်
     ကို English အတိုင်းထားပါ")
3. **Video file** ကို drag & drop ထည့် (သို့) click ပြီးရွေးပါ —
   upload progress bar ပေါ်လာမယ်။ AWS mode မှာ file ကို browser က
   **S3 presigned URL နဲ့တိုက်ရိုက်** တင်ပါတယ် (app server ကို
   မဖြတ်တော့ပါ)။
4. စမ်းသပ်ချင်တာဆို **Use bundled demo clip** နှိပ်ပါ — 14 စက္ကန့်
   demo ဇာတ်ကြောင်းနဲ့ pipeline တစ်ခုလုံးကို ချက်ချင်း
   လည်ပတ်ကြည့်နိုင်ပါတယ်။

---

## ၄။ Processing စာမျက်နှာ (Pipeline)

Upload ပြီးရင် ဒီ pipeline အတိုင်း အလိုအလျောက် လည်ပါမယ် —

```
Upload → Extract audio → Transcribe → Translate/rewrite → (ရပ်)
→ Generate voice → Align timing → (ရပ်)
→ Lip-sync (ပါဝင်ရင်) → Render → Completed
```

- အဆင့်တစ်ခုစီမှာ `pending / running / completed / failed` အခြေအနေ
  ပေါ်ပါတယ်၊ running ဖြစ်နေရင် progress % ပါပြပါမယ်။
- **Logs** ခလုတ်နဲ့ အဆင့်အသေးစိတ် log ဖွင့်ကြည့်နိုင်ပါတယ်
  (အချိန်ပါ timestamp တွေ၊ ffmpeg output၊ error trace)။
- အဆင့်တစ်ခု fail ရင် **Retry** နှိပ်ပြီး အဲ့အဆင့်တစ်ခုတည်းကိုပဲ
  ပြန်စနိုင်ပါတယ် — project တစ်ခုလုံး ပြန်စမထားပါဘူး။
- **Cancel** နှိပ်လိုက်ရင် လက်ရှိအလုပ်တွေ ရပ်သွားပြီး
  `Resume pipeline` နဲ့ ဆက်နိုင်ပါတယ်။
- Processing က **server ပေါ်မှာ** လုပ်တာမို့ browser ပိတ်လိုက်လည်း
  ဆက်လုပ်နေမယ်၊ page refresh လုပ်လည်း အခြေအနေ မပျောက်ပါဘူး။

Pipeline က `AWAITING_USER_REVIEW` (စာတွေပြင်ဖို့) နဲ့
`AWAITING_VOICE_APPROVAL` (အသံတွေစစ်ဖို့) ဆိုတဲ့ အချက် ၂ နေရာမှာ
ရပ်ပြီး မင်းရဲ့ အတည်ပြုချက်ကို စောင့်ပါမယ်။

---

## ၅။ Transcript & Translation Editor

Pipeline က `AWAITING_USER_REVIEW` ဖြစ်သွားရင် Editor tab ကို သွားပါ။
စာမျက်နှာ အစီအစဉ် —

- **ဘယ်ဘက်** — video player (မူရင်း video)
- **အောက်ခြေ** — timeline (အစိမ်းရောင် block တွေ = segment တွေ) +
  segment စာရင်း (scroll လုပ်နိုင်)
- **ညာဘက်** — ရွေးထားတဲ့ segment ရဲ့ ပြင်ဆင်မှု panel

Timeline မှာ block တစ်ခုကို နှိပ်ရင် အဲ့ segment ကို ရွေးပြီး video က
segment စချိန်ကို ချက်ချင်း ရောက်သွားပါမယ်။ Video ဖွင့်လိုက်ရင်
အနီရောင် playhead က timeline ပေါ်မှာ လိုက်လှုပ်ပါမယ်။

### Segment တစ်ခုချင်းစီမှာ ပြင်ဆင်နိုင်တာတွေ

| Field | ရှင်းလင်းချက် |
|---|---|
| Speaker | ပြောသူနာမည် (SPEAKER_00 စသဖြင့် auto ထုတ်ပေးထားတယ်) |
| Start / End (s) | segment စ/ဆုံး အချိန် — ပြင်လိုက်ရင် timing အသစ်နဲ့ ပြန်ညှိပါမယ် |
| Original | မူရင်းဘာသာစကားပိုဒ် |
| Translated / rewritten | dub သုံးမယ့် ပြန်ဆိုထားတဲ့ စာ — မင်းက အဓိက ပြင်ရမှာ။ ပြင်ပြီးရင် အဲ့ segment ရဲ့ အသံဟောင်းကို ဖျက်ပြီး regenerate လုပ်ရမယ် |
| Voice | အသံ ရွေးချယ်မှု (မြန်မာ/English female-male voice ၈ခု) |
| Emotion / style | neutral, happy, sad, dramatic, calm, energetic |
| Speech speed | ×0.7 – ×1.6 slider — auto-stretch နဲ့ ပေါင်းပြီး အသံရှည်တို ညှိတာ |

**Play buttons** — `▶ Voice` (ထုတ်ပြီးသား dub အသံနားထောင်)၊
`Play original slot` (မူရင်း video က အဲ့ segment အချိန်ကို ဖွင့်ပြ)။

**Regenerate voice** — အဲ့ segment တစ်ခုတည်းရဲ့ အသံကိုပဲ ပြန်ထုတ်ပါမယ်။
အခြား segment တွေကို မထိပါဘူး။

**Approve** — အသံထွက်ပြီးသား segment ကို အတည်ပြုပါမယ်။

စာတွေအားလုံး ပြင်ပြီးသွားရင် အပေါ်မှာရှိတဲ့
**Generate all voices & continue** ကို နှိပ်ပါ — pipeline က
segment အားလုံးရဲ့ အသံတွေထုတ်ပြီး timing ညှိပေးမယ်။

---

## ၆။ Voice Review (အသံ စစ်ဆေးခြင်း)

`AWAITING_VOICE_APPROVAL` ရောက်ရင် ဒီ tab မှာ —

| Column | အဓိပည်း |
|---|---|
| Original | မူရင်း စကားပြောချိန် အရှည် |
| Generated | dub အသံရဲ့ အရှည် (timing ညှိပြီး) |
| Diff | ကွာခြားချက် — စိမ်း (≤0.3s အဆင်ပြေ)၊ ဝါ (≤1s သတိထား)၊ အနီ (ရှည်လွန်း) |
| Play | 🎬 = မူရင်း slot နားထောင် / 🔊 = dub အသံနားထောင် |
| Speed | slider နဲ့ အမြန်နှုန်း ချိန် — ချက်ချင်း ပြန်ညှိပေးမယ် |
| Actions | 🔄 regenerate / accept |

အသံက slot ထက် ရှည်နေရင် app က ကြိုတင်ပြောပေးမယ် —
*"Generated voice is +0.9s vs the original slot (2.4s) even after 35%
speed-up. Shorten the text or increase speed."* — ဒါဆိုရင် Editor
မှာ စာတိုအောင်ဖြတ်၊ သို့မဟုတ် speed တိုးပါ။

အပေါ်ဘက်မှာ **original background volume** slider ရှိပါတယ် —
မူရင်း တေးဂီတ/အသံထူးတွေကို ဘယ်လောက်အထိ ထားချင်လဲ
(0% = အားလုံးဖျက်၊ 15% = default၊ 60% = ကြားသလောက်)။

အဆင်ပြေရင် **Approve & render →** (သို့) lip-sync mode ဖြစ်နေရင်
**Approve & lip-sync →** နှိပ်ပါ။

---

## ၇။ Lip-Sync Review (beta — mode မှာ ဖွင့်ထားမှသာ ပေါ်မယ်)

- App က ပထမဆုံး **10–30 စက္ကန့် preview** တစ်ခုကိုပဲ ထုတ်ပြပါမယ်
  — တစ်ခုလုံးကို မစစ်ရသေးဘဲ ရှေ့ဆက်ခင်းကြည့်ဖို့။
- **Face quality warning** — မျက်နှာတစ်ဖက်စောင်းနေ၊ ပိတ်ဆို့နေ၊
  လှုပ်ရှားနေ၊ ပြောသူတစ်ယောက်ထက်ပိုနေရင် သတိပေးပါမယ်
  (ရှင်းလင်းဘယ်လို fail တယ်ဆိုတာ ပါ)။
- **Retry** / **Approve & render final video** /
  **Continue with audio-only dubbing** — lip-sync ဘယ်လောက်ပဲ ဆိုးသွားသွား
  audio-only dub ရလဒ်က အမြဲတန်း ရှိနေမယ်၊ ဘာမှ မဆုံးရှုံးပါဘူး။

> ⚠️ Mock provider မှာ preview က တကယ့် lip-sync မဟုတ်ပါ — ရုပ်ပုံအပေါ်
> dub အသံတပ်ပေးတာပါ။ တကယ့် lip-sync အတွက် GPU worker
> (SageMaker adapter) ချိတ်ရမယ်။

---

## ၈။ Export (ထွက်ပစ္စည်းများ)

Project `COMPLETED` ဖြစ်ရင် Export tab မှာ ဒီတွေ ထုတ်နိုင်ပါတယ် —

- **Final MP4 (dubbed)** — နောက်ဆုံး dub ရုပ်ပုံ (1080p အထိ)
- **720p preview MP4** — အမြန်ကြည့်ဖို့ + "PREVIEW" watermark
  toggle လုပ်နိုင်
- **Final MP4 (burned-in subtitles)** — စာတန်းထိုးပြီး
- **Dubbed audio WAV / MP3** — အသံတစ်ခုတည်း
- **MP4 with selectable audio tracks** — dub + မူရင်းအသံ နှစ်ခုလုံးပါ
  (VLC/mpv မှာ ပြောင်းကြည့်နိုင်)
- **Subtitles SRT/VTT** — ဘာသာနှစ်မျိုးလုံး (source + target၊ ဒါပေမယ့်
  မင်းပြင်ထားတဲ့ စာသားအတိုင်း)

Render နှိပ်လိုက်တဲ့ တစ်ချက်ချင်းစီမှာ job status ပေါ်ပါမယ်၊
ပြီးရင် **Download** နှိပ်ယူနိုင်ပါတယ်။ AWS mode မှာ file အားလုံးက
S3 output bucket မှာ သိမ်းထားပါတယ်။

---

## ၉။ Real Providers ချိတ်ခြင်း

### ၉.၁ ဘာသာပြန် / ပြန်ရေး (LLM)

OpenAI-compatible API တစ်ခုခု (OpenAI, OpenRouter, local Ollama/LM Studio…)
ချိတ်နိုင်ပါတယ် —

```bash
export TRANSLATION_PROVIDER=llm
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_API_KEY="sk-..."
export LLM_MODEL="gpt-4o-mini"
```

App က segment အားလုံးကို batch တစ်ခုတည်းနဲ့ ပို့ပြီး
"dubbing-friendly သဘာဝကျတဲ့ ပြန်ဆိုချက်" တောင်းပါမယ်။ မင်းရဲ့
project instructions တွေပါ ပါဝင်ပါမယ်။

### ၉.၂ အသံထုတ် (TTS)

မြန်မာလုံးဝ ပြောနိုင်တဲ့ TTS service တစ်ခုခု (ကိုယ်တိုင် run တဲ့
MM-TTS model သို့ commercial API) ကို HTTP adapter နဲ့ ချိတ်ပါ —

```bash
export TTS_PROVIDER=http
export TTS_HTTP_URL="https://your-tts-service.example.com/synthesize"
export TTS_HTTP_KEY="..."          # optional Bearer token
export TTS_HTTP_FORMAT="wav"       # service ပြန်ပေးတဲ့ format
```

Service ကို မျှော်မှန်းထားတဲ့ contract —

```
POST {TTS_HTTP_URL}
{ "text": "...", "voice_id": "my-female-01", "speed": 1.0,
  "language": "my", "emotion": "neutral" }
← 200 OK + audio bytes (wav/mp3)
```

### ၉.၃ Amazon Transcribe

AWS မှာ deploy ထားရင် (S3 mode + IAM role ပါဝင်ပါမယ်) —

```bash
export TRANSCRIPTION_PROVIDER=aws
```

### ၉.၄ GPU Lip-sync

SageMaker async endpoint (Wav2Lip model) ထောင်ပြီး —

```bash
export LIPSYNC_PROVIDER=sagemaker
export LIPSYNC_ENDPOINT_NAME="my-wav2lip-endpoint"
```

Template — `infrastructure/sagemaker/lipsync-endpoint.yaml`

> 🔑 API key တွေကို frontend မှာ ဘယ်သောအခါမှ မထားပါနဲ့ — env var
> သို့မဟုတ် AWS Secrets Manager ကနေပဲ ဖတ်ပါ (AWS guide ပိုင်း ကြည့်ပါ)။

---

## ၁၀။ မေးလေ့ရှိတဲ့အချက်များ

**Q — browser ပိတ်လိုက်ရင် processing ဆက်လုပ်နေမလား?**
ရပါတယ်။ Pipeline တစ်ခုလုံးက server ရဲ့ background worker မှာ
လုပ်တာမို့ browser နဲ့ မသက်ဆိုင်ပါဘူး။ ပြန်ဖွင့်ရင် နောက်ဆုံး
အခြေအနေနဲ့ ဆက်တွေ့ပါမယ်။

**Q — segment တစ်ခု fail ရင် တစ်ခုလုံး ပြန်စရလား?**
မလိုပါဘူး။ Failed segment ကိုပဲ Regenerate နှိပ်ပါ — အခြား segment
တွေရဲ့ အသံတွေ မထိခိုက်ပါဘူး။

**Q — အသံက အချိန်ထက် ရှည်နေတယ်၊ ဘယ်လိုလုပ်မလဲ?**
(က) စာကို တိုအောင်ဖြတ်ပါ၊ (ခ) speed slider တိုးပါ၊ (ဂ) ဒါတောင်
မတော့ရင် segment ရဲ့ End time ကို သင့်တော်သလောက် တိုးပေးပါ
(နောက် segment နဲ့ ထပ်မသွားစေဘဲ)။

**Q — မူရင်း တေးဂီတ ကြားချင်တယ်။**
Voice Review tab မှာ background volume slider ကို တိုးပါ (60% အထိ)။

**Q — ဒေတာတွေ ဘယ်မှာ သိမ်းလဲ?**
Local mode — `backend/data/` (SQLite + media files)။
AWS mode — RDS PostgreSQL + S3 buckets နှစ်ခု (input/output)။
