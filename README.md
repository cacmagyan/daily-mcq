# Daily CA & CMA MCQ agent

Every day this agent writes one MCQ for each of six courses, draws a **question image** and an **answer image** for each, and posts each pair to Instagram as a two-slide carousel (swipe for the answer). It also posts one **Concept of the day**: a 4-slide handwritten-notebook note, and one **MCQ reel**: a 15-second video of one of the day's MCQs (both below).

Each course has its own colour, so students can spot their MCQ in the feed and on your profile grid:

| Course | Colour | Posts at (IST) |
|---|---|---|
| CA Foundation | 🟩 green | 07:55 |
| CMA CAT | 🟨 yellow | 09:55 |
| CA Inter | 🟦 blue | 12:25 |
| CMA Inter | 🟧 orange | 15:25 |
| CA Final | 🟪 purple | 18:25 |
| CMA Final | 🟥 red | 20:55 |

The images are designed as an OMR answer sheet printed in the course colour. On the answer slide the correct bubble is filled in with pencil, followed by the explanation, the rough work, why the other options are wrong, and an exam tip.

## How a day works

The agent runs in **auto** mode (`review: mode: "auto"` in `config.yaml`): MCQs post without waiting for you.

1. **18:47, every evening.** The agent writes tomorrow's six MCQs with Claude. A second, separate Claude call solves each one *without seeing the answer*. If it gets a different answer, the MCQ is rewritten (up to 3 tries). Then it draws the 12 images, approves the day itself and opens a GitHub **issue** called "MCQs for <date> (Day N)" with every image.
2. **If an MCQ has a serious problem**, it is put **on hold** and won't post. The issue title starts with "⛔ Action needed" and you are @mentioned, so GitHub notifies you that evening. Serious means: the checker could not confirm the answer key after 3 tries, or the text doesn't fit the image and is cut off. Smaller notes (shrunk text, ⚖️ law topics) don't stop anything.
3. **Early next morning (05:47 and 06:47).** If the evening runs couldn't write the day (for example the Claude usage limit was reached), these runs write whatever is missing or failed for today, before the first post.
4. **Next day.** Each course posts at its time. The issue shows ✅ and a link as each one goes out, and closes itself after the last post.

**A pause in posting** (e.g. the Claude subscription lapsed): add the dates to `brand: paused` in `config.yaml` and the Day numbers carry on after them (no gap). Days already drawn with the old number are redrawn by the next run, without Claude.

**Preparing days ahead.** Actions → **6. Prepare days ahead** → Run workflow (default 14 days). It prepares one day after another, saving each as it finishes, until the days are ready, Claude's usage limit is reached, or about 4.5 hours pass; it also runs every night at 23:17 to top the buffer up. Prepared days post by themselves without Claude, so a buffer keeps the page going if Claude can't be used for a while. `models: strong_checks: "law_tax_audit"` keeps the strong checker for tax, law, audit and SM papers only, which roughly halves the usage.

To act on a day, comment on its issue:

| Comment | What it does |
|---|---|
| `/approve ca_inter` | post a held MCQ as it is |
| `/regen ca_inter` | replace it with a new MCQ; it posts by itself if the check passes |
| `/regen cma_final make it a numerical on WACC` | the same, with an instruction |
| `/hold ca_final` | stop an MCQ from posting (until you `/approve` or `/regen` it) |

- **Change text:** edit `queue/<date>/mcqs.json` on the main branch (pencil icon). The images redraw themselves in about two minutes.
- Course ids: `ca_foundation`, `cma_cat`, `ca_inter`, `cma_inter`, `ca_final`, `cma_final`.
- Something already posted can't be changed by the agent; edit or delete it in the Instagram app.

**Prefer to approve every day yourself?** Set `mode: "github_pr"`. The evening job then opens a pull request instead, and nothing posts until you merge it. `/regen` works in the pull request too.

## Concept of the day

One post a day at **19:40**, one course a day in turn (CA Foundation, CMA CAT, CA Inter, CMA Inter, CA Final, CMA Final). It is a 4-slide carousel in the Costing Concept Book style: cream ruled notebook page, red marker titles, handwriting, pastel cards and doodles, with the course colour on the top label.

1. **Concept**: title, "In simple words", definition cards, key points.
2. **Formula**: formulas with symbol legends, or a comparison table for theory and law topics, plus a key insight.
3. **Study trick**: a memory trick, how to attempt it in the exam, an exam tip and a doubt buster.
4. **Common mistakes**: what students write wrongly and the correct way, and "Save this for revision!".

- The paper is the one tomorrow's MCQ for that course uses, and **tomorrow's MCQ tests the concept**. Slide 4 tells students so.
- **Who signs it:** papers marked `author: ranjith` in `config.yaml` (law, Strategic Management and audit papers) say **Ranjith Shivahari**; all others say **Rahul kp**. CMA Inter Papers 9 and 10 are split into their two halves, each with its own author.
- A second Claude call checks every statement and formula. If it still finds an error after 3 tries, or the text doesn't fit, the note is held and the day's issue tells you, exactly like an MCQ. Use `/approve concept`, `/regen concept` (a new note on the same concept; add an instruction to change it) or `/hold concept`. The text is in `queue/<date>/concept.json`.
- Settings are under `concepts:` in `config.yaml` (`start_date`, `post_time`, course order).
- **Adding a note to a day that's already prepared** (for example after moving `start_date` earlier): Actions → 1. Prepare tomorrow's MCQs → Run workflow, type the date, tick **concept only**. The MCQs stay as they are. If tomorrow's MCQ already exists, the note is written on that MCQ's topic and paper. The evening run does this by itself for tomorrow. The handwriting fonts (Permanent Marker, Patrick Hand, Caveat; free licences) are downloaded by GitHub the first time they are needed.

## MCQ reel of the day

One Reel a day at about **6:00 PM** (`post_time: "17:55"`; Instagram takes a minute or two to process the video). It shows one of the day's MCQs on the OMR sheet with an **8-second countdown** and ticking (faster for the last 3 seconds). Then a chime plays, the correct bubble is filled in and the reason appears for 7 seconds.

- **The paper's author presents it:** thinking while the clock runs, pointing at the reason when the answer shows, and a thumbs-up with "Follow" at the end. The pictures are `assets/brand/rahul-think.png`, `-point.png`, `-thumbs.png` and the same three for `ranjith-`. If an MCQ's text is too long to fit beside the presenter, that reel is drawn without him.
- **Share line:** at the end the header says "Send this to a friend who'd pick option B 😄", naming one of the wrong options (it changes daily). Instagram counts shares heavily when deciding whether to show a reel to new people.
- **AI voiceover** (needs a voice key, see "Reel voice" below): the presenter says "CA Inter question. Can you answer it in 8 seconds?", then reads the answer and the reason, then asks viewers to share. The answer stays on screen until he finishes, so a voiced reel is about 25-30 seconds. Rahul and Ranjith have different Indian English voices (`reels: voice:` in `config.yaml`).
- It reuses an MCQ that has already passed every check, so nothing new is written and no extra Claude calls are made. One course a day, in the order under `reels:` in `config.yaml` (never the same course as that day's concept note).
- **It follows its MCQ:** if that MCQ is on hold or failed, the next course is used. If the MCQ is put on hold or edited after the video was made, the reel doesn't post until it is remade (an edit to `mcqs.json` remakes it by itself).
- The day's issue shows the reel's first frame with a **▶ Watch the reel** link. Commands: `/regen reel` (make it again), `/hold reel`, `/approve reel`.
- It's a normal Reel (feed and Reels tab). Set `trial: true` to post Trial Reels instead: Instagram shows those first only to people who don't follow you.
- The sound is generated by the agent (ticks and a chime), so there are no music rights to worry about. Instagram's API can't add songs from its music library.
- **Adding a reel to a day that's already prepared:** Actions → 1. Prepare tomorrow's MCQs → Run workflow, type the date, tick **reel only**. The evening run does this by itself for tomorrow.
- Video files are made with ffmpeg, which the workflows install when GitHub doesn't already have it.

## Stories and Highlights

Right after each post goes out, a **Story** follows: the MCQ's question in its course colour ("Reply with A, B, C or D · Answer: tap @cacmagyan ↖"; Stories posted by the API can't link straight to a post), the concept note's first slide, and the reel itself. Story replies arrive as DMs. Settings are under `stories:` in `config.yaml`; a Story that fails is tried again on the next run, but not more than 6 hours after its post.

Instagram's API can't add poll stickers or Highlights, so these stay in the app:
- **Highlights** (once): make one per course plus Concepts and Reels, using the covers `highlight-1-ca_foundation.jpg` … `highlight-8-reels.jpg` (sent separately). Names: CA Foundation, CMA CAT, CA Inter, CMA Inter, CA Final, CMA Final, Concepts, Reels.
- **Each week (2-3 minutes):** open each Highlight → Add → tick that week's Stories in its colour. Stories stay in your Archive, so nothing is lost if you skip a week.
- **A real poll** on a day you like: post that Story yourself from the app and add the poll sticker.

### Reel voice

The voice comes from an official text-to-speech service; add **one** of these as GitHub secrets (Settings → Secrets and variables → Actions). Without a key, reels have ticks and a chime only. A reel uses about 600 characters of speech a day, well inside both free tiers.

**Azure Speech (recommended):**
1. Sign in at portal.azure.com (a free Microsoft account; Azure asks for a card to verify you, and the free tier isn't charged).
2. **Create a resource** → search **Speech** → Create. Region: **Central India**; pricing tier: **Free F0**. Review + create.
3. Open it → **Keys and Endpoint**. Copy **KEY 1** and the **Location/Region** (`centralindia`).
4. Add secrets `AZURE_SPEECH_KEY` (the key) and `AZURE_SPEECH_REGION` (`centralindia`).

**Or Google Cloud Text-to-Speech:** enable the Text-to-Speech API in a Google Cloud project, create an API key restricted to that API, and add it as the secret `GOOGLE_TTS_API_KEY`.

**Hear it:** Actions → **5. Reel demo** → Run workflow. In a couple of minutes the run's summary has links to two demo reels (Rahul and Ranjith). Nothing is posted. The day's report shows 🔊 with the voice used, or 🔇 and the reason.

## What you need

- An Instagram **professional** account (Creator or Business).
- A free **Meta developer** app, to get an Instagram access token.
- **Claude**: either your existing **Claude Pro or Max subscription** (no extra cost), or a Claude API key (pay per use).
- A free **GitHub** account. GitHub runs everything on schedule, so your computer can stay off.

## Setup (once, about 45 minutes)

### 1. Instagram
In the Instagram app: Settings → Account type and tools → Switch to professional account. Creator or Business both work.

### 2. Instagram access token
1. Go to <https://developers.facebook.com>, log in, and create an app (type **Business**).
2. Add the **Instagram** product and open **API setup with Instagram login**.
3. Under *Generate access tokens*, add your Instagram account and generate a token. It needs the permissions `instagram_business_basic` and `instagram_business_content_publish`.
4. Copy the token. It lasts 60 days, and workflow 5 renews it every week, so you only do this once.

You are only posting to your own account, so App Review is normally not needed. Meta changes its dashboard often; if a screen looks different, the same steps are in Meta's guide "Instagram API with Instagram Login".

### 3. Claude login (choose one)

**Option A: your Claude Pro or Max subscription (no extra cost).** On your Mac, open Terminal and run:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Open a new Terminal window and run `claude setup-token`. Your browser opens; sign in with your Claude account and approve. The terminal then prints a long token. Save it as the GitHub secret `CLAUDE_CODE_OAUTH_TOKEN` (step 4). It lasts one year, so put a reminder in your calendar to make a new one.

**Option B: a Claude API key (pay per use, about $3-6 a month).** At <https://platform.claude.com>: API keys, then Create key. Add credit under Billing. Save it as the secret `ANTHROPIC_API_KEY`.

If you add both, the agent uses your subscription and falls back to the API key only if the subscription token fails.

### 4. GitHub
1. Create a new repository. **Make it public.** Instagram downloads the images from it, and it cannot read a private repo. Your keys stay private either way, because they are stored as encrypted secrets. (Want a private repo? See "Private repo" below.)
2. Upload everything from this folder, **including the hidden `.github` folder** (on a Mac, press Cmd+Shift+. in Finder to see it). GitHub Desktop is the easiest way.
3. **Settings → Secrets and variables → Actions → New repository secret**, add:

   | Secret | Value |
   |---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | from `claude setup-token` (Claude subscription), **or** |
   | `ANTHROPIC_API_KEY` | your Claude API key |
   | `IG_ACCESS_TOKEN` | the Instagram token from step 2 |
   | `GH_ADMIN_TOKEN` | a GitHub token that can update secrets (below) |
   | `IG_USER_ID` | optional; found automatically |

   To make `GH_ADMIN_TOKEN`: your GitHub profile → Settings → Developer settings → Fine-grained tokens → Generate new token. Repository access: *only this repository*. Permissions: **Secrets: Read and write**. Choose the longest expiry and put a reminder in your calendar to replace it.
4. **Settings → Actions → General → Workflow permissions:** choose *Read and write permissions* and tick **Allow GitHub Actions to create and approve pull requests**. Save.
5. On the repository page, click **Watch → All activity** so the evening report reaches your phone.

### 5. Your details
Open `config.yaml` (pencil icon on GitHub) and set:
- `handle`: your Instagram handle, e.g. `"@rahulkp.cma"`. It appears on every image and caption.
- `start_date`: the date of Day 1.

### 6. Test it
1. **Actions → 1. Prepare tomorrow's MCQs → Run workflow**, tick **sample**, run. In about 5 minutes a pull request appears with the 12 sample images. This checks the setup without using Claude. **Close it; don't merge it**, or the samples will be posted.
2. Run it again **without** sample. This writes real MCQs with Claude. Review the pull request.
3. **Actions → 4. Publish due MCQs → Run workflow** with *dry run* ticked. The log shows exactly what would be posted.
4. To post something today: run Prepare with today's date in the *date* box, merge the pull request, then run Publish with *dry run* unticked. Everything whose time has passed is posted, two per run.

From then on it runs by itself.

## Your daily routine

- **Nothing to do** on most days. Look at the posts on Instagram whenever you like.
- **When GitHub notifies you** ("⛔ Action needed"), open the issue that evening, read why the MCQ was held, and comment `/approve <course>` or `/regen <course>`. A held MCQ posts at its time if you release it before then; otherwise at the next run (the 20:57 run posts everything still waiting).
- Turn on notifications: repository page → **Watch → All activity**, and allow notifications in the GitHub app.

## Accuracy

How the agent catches its own mistakes, so you don't have to check every subject:
- **Arithmetic is re-done in code.** For a numerical MCQ, Claude also writes its calculation as plain arithmetic; the agent runs it, and the answer key must match the result exactly (and no wrong option may match it).
- **A stronger, separate checker** (`models.checker`, Claude Opus) solves every MCQ without seeing the key. Tax and law MCQs must also be solved correctly by a second checker. Concept notes are checked by two checkers that re-derive every table cell, sign and formula.
- **Known traps** (`traps.yaml`): every mistake found is written down there once; the writer and the checkers read the matching traps each time, so it can't happen again. Add a trap with one or two plain sentences.
- **Topic switch before holding:** if an MCQ or note still can't be confirmed after 3 tries, the agent writes one on a different, core topic. Only if that also fails is it held, and you're told.

- Claude writes to strict rules: original questions only (never copied from study material, RTPs, MTPs or past papers), one correct answer, distractors built from real student mistakes, Indian number formats, and no made-up section numbers.
- A second Claude call solves every MCQ independently. Disagreements are rewritten or flagged.
- Tax papers follow the law set in `config.yaml → law_basis`, which changes by date. CA tax questions switch from the Income-tax Act, 1961 to the **Income-tax Act, 2025** on 1 Feb 2027, because ICAI examines the new Act from the May 2027 attempt. **Update `law_basis` when ICAI or ICMAI publish each attempt's applicability notice.**
- You approve every post. AI can still get a rate, limit or amendment wrong, so read the ⚖️ ones carefully.

## Changing things

| To change | Edit |
|---|---|
| Colours, course names, hashtags (Instagram allows 5), papers, order of papers | `config.yaml` |
| Posting times | `post_time` in `config.yaml` **and** the matching cron line in `.github/workflows/publish.yml`. Cron is UTC: subtract 5 h 30 m from IST, and set the run a couple of minutes after `post_time`. |
| Evening preparation time | cron line in `.github/workflows/prepare.yml` |
| Image design | `templates/slide.html.j2` (reel: `templates/reel.html.j2`) |
| Reel timer, order of courses, Trial Reels | `reels:` in `config.yaml` |
| Claude model | `models` in `config.yaml` |
| Signature name | `brand.name` in `config.yaml` |
| Logo (top right of every image) | `python -m mcq_agent set-logo path/to/logo.png` (needs `pip install numpy scipy`). It removes a fake checkerboard "transparent" background automatically. Set `brand.logo: ""` for no logo. |

Papers rotate one per day per course, in the order listed in `config.yaml`. List a paper twice to give it more days.

## Private repo

Set `image_hosts: ["cloudinary"]` in `config.yaml`, create a free Cloudinary account, and add a secret `CLOUDINARY_URL` (it looks like `cloudinary://KEY:SECRET@CLOUD_NAME`, shown on the Cloudinary dashboard). Images in the review pull request still display on the GitHub website, though possibly not in the mobile app.

## Running on your own computer (optional)

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env                 # then fill in your keys

python -m mcq_agent prepare --date today --sample   # sample images, no API key needed
python -m mcq_agent prepare                          # tomorrow's real MCQs
#   look at queue/<date>/preview.jpg, edit queue/<date>/mcqs.json, then:
python -m mcq_agent render --date 2026-10-20         # redraw after editing
python -m mcq_agent regen --date 2026-10-20 --course ca_inter --instruction "make it on CVP"
python -m mcq_agent check                            # test Claude + Instagram connections
python -m mcq_agent publish --dry-run                # show what is due now
python -m unittest discover tests                    # offline tests
```

For local-only use, set `review.mode: local` in `config.yaml` and approve with `python -m mcq_agent approve --date <date>`. Instagram still needs public image URLs, so use Cloudinary or push the batch to the public GitHub repo first.

## Costs and limits

- **GitHub Actions:** free for public repositories.
- **Claude:** about 12 calls a day (6 writes + 6 checks), more when an MCQ is rewritten. With a subscription token this counts toward your plan's normal usage; each call is small. With an API key, expect roughly $3-6 a month; check usage in the Console after the first week.
- **Instagram:** the API allows 100 posts per 24 hours; this uses about 16 (6 MCQs, the concept note, the reel and a Story after each). A carousel counts as one post.
- **Repository size:** images and the reel add roughly 4 MB a day (about 1.5 GB a year). That is fine for a long while; switch to Cloudinary if you want the repo to stay small.

## Troubleshooting

| Problem | Fix |
|---|---|
| Prepare fails: "GitHub Actions is not permitted to create or approve pull requests" | Setup step 4.4 |
| Images in the pull request don't load | The repo is private: make it public or see "Private repo" |
| Publish: "No image host worked" | Same as above. Also check the batch was merged into the main branch |
| Instagram error 190 (token) | Make a new token (setup step 2) and update the `IG_ACCESS_TOKEN` secret. Check `GH_ADMIN_TOKEN` hasn't expired, so renewals can save. |
| Claude error 401 or 404 | Wrong API key, or the model name in `config.yaml` isn't available to your account |
| "Claude subscription token was refused" | The token expired (after a year) or was revoked. Run `claude setup-token` again and update the `CLAUDE_CODE_OAUTH_TOKEN` secret |
| A course shows ⛔ or ❌ in the day's issue | Comment `/regen <course_id>`, or `/approve <course_id>` to post it anyway |
| Text looks small on an image | The text was long and was shrunk to fit. Shorten it in `mcqs.json` |
| Nothing was posted | Open Actions → 4. Publish due MCQs to read the log. In github_pr mode, check the pull request was merged |
| A comment did nothing | It must start with the command, e.g. `/approve ca_inter`, on the issue titled "MCQs for <date>" |

## Files

```
config.yaml                 courses, colours, times, papers, law basis
mcq_agent/                  the agent (generator, renderer, Instagram publisher)
templates/slide.html.j2     the image design (reel.html.j2: the reel, concept.html.j2: the concept note)
assets/fonts/               bundled fonts, so images look identical everywhere
assets/brand/logo.png       your logo, background removed
samples/sample_batch.json   six hand-checked sample MCQs
queue/<date>/               each day's MCQs (mcqs.json), images, concept note, reel (reel.json, reel.mp4), and what was posted
.github/workflows/          the scheduled jobs (and 5. Reel demo, run by hand)
demo/                       demo reels made by "5. Reel demo"
tests/                      offline tests
```

MCQs are original practice questions written for students. This project is not affiliated with ICAI or ICMAI.
