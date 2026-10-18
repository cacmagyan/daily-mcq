# Daily CA & CMA MCQ agent

Every day this agent writes one MCQ for each of six courses, draws a **question image** and an **answer image** for each, waits for your approval, and posts each pair to Instagram as a two-slide carousel (swipe for the answer).

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

1. **18:47, every evening.** The agent writes tomorrow's six MCQs with Claude. A second, separate Claude call solves each one *without seeing the answer*. If it gets a different answer, the MCQ is rewritten (up to 3 tries) or flagged for you. Then it draws the 12 images and opens a **pull request** on GitHub with all of them.
2. **You, any time before 07:55 next morning.** Open the pull request on the GitHub app or website, look at the images, and tap **Merge**. Merging = approved. Nothing is ever posted without it.
3. **Next day.** Each course posts at its time.

To fix something before approving:
- **Change text:** edit `queue/<date>/mcqs.json` in the pull request (Files changed → ⋯ → Edit file). The images redraw themselves in about two minutes.
- **Get a new MCQ for one course:** comment `/regen ca_inter`. Add an instruction if you like: `/regen cma_final make it a numerical on WACC`.
- **Skip a day:** close the pull request.

Course ids for `/regen`: `ca_foundation`, `cma_cat`, `ca_inter`, `cma_inter`, `ca_final`, `cma_final`.

## What you need

- An Instagram **professional** account (Creator or Business).
- A free **Meta developer** app, to get an Instagram access token.
- A **Claude API key** from the Anthropic Console (pay per use).
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

### 3. Claude API key
At <https://console.anthropic.com>: API keys → Create key. Add some credit under Billing.

### 4. GitHub
1. Create a new repository. **Make it public.** Instagram downloads the images from it, and it cannot read a private repo. Your keys stay private either way, because they are stored as encrypted secrets. (Want a private repo? See "Private repo" below.)
2. Upload everything from this folder, **including the hidden `.github` folder** (on a Mac, press Cmd+Shift+. in Finder to see it). GitHub Desktop is the easiest way.
3. **Settings → Secrets and variables → Actions → New repository secret**, add:

   | Secret | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | your Claude API key |
   | `IG_ACCESS_TOKEN` | the Instagram token from step 2 |
   | `GH_ADMIN_TOKEN` | a GitHub token that can update secrets (below) |
   | `IG_USER_ID` | optional; found automatically |

   To make `GH_ADMIN_TOKEN`: your GitHub profile → Settings → Developer settings → Fine-grained tokens → Generate new token. Repository access: *only this repository*. Permissions: **Secrets: Read and write**. Choose the longest expiry and put a reminder in your calendar to replace it.
4. **Settings → Actions → General → Workflow permissions:** choose *Read and write permissions* and tick **Allow GitHub Actions to create and approve pull requests**. Save.
5. On the repository page, click **Watch → All activity** so the evening pull request reaches your phone.

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

## Your daily routine (about 2 minutes)

- Open the evening pull request. Look at rows flagged ⚠️ (the checker wasn't fully sure) or ⚖️ (tax or law: check rates and sections) first.
- Merge to approve, or edit or `/regen` first.
- If you forget, the 07:57 run fails and GitHub emails you. Merge whenever you see it: the remaining courses still post on time, and courses whose time has passed catch up at the next runs (two per run; the 20:57 run posts everything still waiting).

## Accuracy

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
| Image design | `templates/slide.html.j2` |
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
- **Claude:** about 12 API calls a day (6 writes + 6 checks), more when an MCQ is rewritten. Check your usage in the Anthropic Console after the first week.
- **Instagram:** the API allows 100 posts per 24 hours; this uses 6. A carousel counts as one post.
- **Repository size:** images add roughly 2.5 MB a day (about 1 GB a year). That is fine for a long while; switch to Cloudinary if you want the repo to stay small.

## Troubleshooting

| Problem | Fix |
|---|---|
| Prepare fails: "GitHub Actions is not permitted to create or approve pull requests" | Setup step 4.4 |
| Images in the pull request don't load | The repo is private: make it public or see "Private repo" |
| Publish: "No image host worked" | Same as above. Also check the batch was merged into the main branch |
| Instagram error 190 (token) | Make a new token (setup step 2) and update the `IG_ACCESS_TOKEN` secret. Check `GH_ADMIN_TOKEN` hasn't expired, so renewals can save. |
| Claude error 401 or 404 | Wrong API key, or the model name in `config.yaml` isn't available to your account |
| A course shows ❌ in the pull request | Comment `/regen <course_id>` |
| Text looks small on an image | The text was long and was shrunk to fit. Shorten it in `mcqs.json` |
| Nothing was posted | The pull request wasn't merged. Open Actions → 4. Publish due MCQs to read the log |

## Files

```
config.yaml                 courses, colours, times, papers, law basis
mcq_agent/                  the agent (generator, renderer, Instagram publisher)
templates/slide.html.j2     the image design
assets/fonts/               bundled fonts, so images look identical everywhere
assets/brand/logo.png       your logo, background removed
samples/sample_batch.json   six hand-checked sample MCQs
queue/<date>/               each day's MCQs (mcqs.json), images, and what was posted
.github/workflows/          the five scheduled jobs
tests/                      offline tests
```

MCQs are original practice questions written for students. This project is not affiliated with ICAI or ICMAI.
