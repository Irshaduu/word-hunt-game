# Setup checklist

Everything the code can't do by itself: keys from Google and Cloudflare, and settings on Render.

Each feature stays hidden, or falls back to what worked before, until its key is in. So you can push first and add keys later, in any order. Nothing here costs money.

Render does the rest on every deploy: its build command installs `requirements.txt` (one new package, `PyJWT[crypto]`), collects static files, and runs the database migrations on Neon.

## 1. Push the work

The phases are commits on the branch `phases-1-to-6`. Nothing was pushed.

```bash
git push -u origin phases-1-to-6
```

Then open a pull request into `main` on GitHub. The **Tests** check runs on it. Merge when it's green, and Render deploys `main`.

## 2. Sign in with Google (Phase 2, about 10 minutes)

You need a **client ID**. It isn't a secret: it shows in the page source. There is no client secret to keep.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, for example "Word Hunt".
2. **Google Auth Platform → Branding:**
   - App name: Word Hunt. User support email: your Gmail.
   - App home page: `https://word-hunt-game.onrender.com`
   - Privacy policy: `https://word-hunt-game.onrender.com/privacy/`
   - Authorized domain: `word-hunt-game.onrender.com`
3. **Audience:** External, then **Publish app**. The game only asks for Google's basic scopes (openid, email, profile), which need no verification.
4. **Clients → Create client → Web application:**
   - Authorized JavaScript origins:
     - `https://word-hunt-game.onrender.com`
     - for testing on your computer: `http://localhost` and `http://localhost:8000`
   - No redirect URIs: the button hands its result straight to the page.
5. Copy the **Client ID**. It ends in `.apps.googleusercontent.com`.
6. **Render → word-hunt-game → Environment:** add `GOOGLE_CLIENT_ID` = the client ID, then save. Render redeploys.
7. Check: the home page shows **Continue with Google**. Sign in, choose a name, and you're in. On your profile, a PIN account gets a **Sign in with Google** button to link the two.

To try it on your computer, set the same variable before `python manage.py runserver`.

## Optional: lock the Host header

Render → Environment → `DJANGO_ALLOWED_HOSTS` = `word-hunt-game.onrender.com`

Django then answers other host names with 400. It's off by default because a typo here would answer every request with 400. Check the site right after saving.
