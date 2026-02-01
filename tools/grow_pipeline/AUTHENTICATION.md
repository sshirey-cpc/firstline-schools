# Authentication Issue & Solutions

## Current Problem

The Grow API client credentials provided do not work with any standard OAuth 2.0 authentication endpoint:
- Client ID: `6fe43bd0-e8d1-4ce0-a9a9-2267c9a3df9b`
- Client Secret: `18eaec46-c6c9-4bcb-abf7-b36030485966`

All authentication attempts return `401 Unauthorized`.

## What We've Tried

✗ `POST /external/auth` with JSON body
✗ `POST /external/auth` with form data
✗ `POST /external/auth` with Basic Auth
✗ `POST /external/token` with client credentials grant
✗ `POST /oauth/token` with client credentials grant

## Solutions

### Option 1: Manual Token Updates (Temporary)

When your token expires, update it manually:

```bash
# Update token using the helper script
./tools/grow_pipeline/update_token.sh "your-new-bearer-token-here"

# Or edit .env directly
vim .env
# Change: GROW_BEARER_TOKEN=your-new-token
```

**How to get a new token:**
- You'll need to ask Level Data how you obtained the original token
- Or use whatever method you used to get: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

### Option 2: Contact Level Data Support (Recommended)

**Ask Level Data:**

1. **What's the correct authentication endpoint?**
   - Is it `/external/auth`?
   - Or a different endpoint?

2. **What's the correct authentication method?**
   - JSON body with `client_id` and `client_secret`?
   - Basic auth?
   - Different grant type?

3. **Are the client credentials configured correctly?**
   - Are they enabled for OAuth client credentials flow?
   - Do they have the right scopes/permissions?

4. **Do they offer long-lived tokens?**
   - API keys that don't expire?
   - Refresh tokens?

**Email template:**

```
Subject: API Authentication - Client Credentials Not Working

Hi Level Data Support,

We're trying to authenticate programmatically with the Grow API using our client credentials, but getting 401 Unauthorized errors.

Client ID: 6fe43bd0-e8d1-4ce0-a9a9-2267c9a3df9b

Questions:
1. What's the correct authentication endpoint for client credentials flow?
2. What's the expected request format (JSON, form-data, Basic Auth)?
3. Are these credentials enabled for programmatic access?
4. Do you offer long-lived API tokens or refresh tokens?

We need this for automated daily data syncs to BigQuery.

Thank you!
```

### Option 3: Alternative Authentication Flows

If client credentials don't work, ask Level Data about:

**A) API Keys**
- Static keys that don't expire
- Simpler than OAuth

**B) Service Account**
- Dedicated account for automated access
- Username/password that exchanges for token

**C) Refresh Tokens**
- Long-lived tokens that can generate new access tokens
- Standard OAuth 2.0 pattern

## Current Workaround

The pipelines work with manually provided bearer tokens via `.env`:

```bash
GROW_BEARER_TOKEN=your-token-here
```

**Limitations:**
- Tokens expire (current token expires ~Feb 2, 2026)
- Must manually update when expired
- Not suitable for long-term automation

## When Token Expires

You'll see this error:
```
AuthenticationError: Unauthorized
```

**To fix:**
1. Get a new bearer token from Level Data
2. Run: `./tools/grow_pipeline/update_token.sh "new-token"`
3. Re-run the pipeline

## Testing Authentication

To test if auth is working:

```bash
# Test with your bearer token
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://grow-api.leveldata.com/external/assignments?limit=1"

# Should return data, not 401
```

## Next Steps

1. **Contact Level Data** to fix the client credentials authentication
2. Until then, use the **manual token update** process
3. Once fixed, the pipeline will **automatically refresh tokens** without manual intervention

---

**Need help?** Check `tools/grow_pipeline/README.md` or contact the Level Data support team.
