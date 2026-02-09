# Salary Calculator

A static web page that allows FirstLine Schools staff to calculate and compare salaries based on role, experience, and education level.

**Live URL:** https://salary-scale-965913991496.us-central1.run.app

---

## Overview

This calculator helps staff:
- View salary scales for different roles
- Calculate salary based on years of experience
- See salary progression over time
- Compare different role options

---

## Tech Stack

- Static HTML with Tailwind CSS
- No backend required
- Deployed on Google Cloud Run

---

## Deployment

```bash
gcloud run deploy salary-scale \
  --source . \
  --region us-central1 \
  --project talent-demo-482004 \
  --allow-unauthenticated
```

---

## Contact

For questions about salary scales:
- talent@firstlineschools.org
- hr@firstlineschools.org
