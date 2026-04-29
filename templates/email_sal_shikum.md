# Custom Campaign Template Example — Non-English Outreach

This file shows how to create a campaign that targets a specific audience in a non-English language.

Use this as a starting point when:
- Your target audience communicates in a language other than English
- You have a specific contact list (not the generic Tier1/2/3 pipeline)
- You want a shorter, simpler email sequence (2-3 emails max)

---

## Setup overview

1. **Prepare your contact CSV** with at minimum: `org_name`, `email`, `contact_name` (optional)
2. **Import contacts** via `step0_import.py --campaign my_campaign --csv data/my_contacts.csv`
3. **Add email logic** to `step6_send_emails.py` in the `build_email()` function
4. **Add to workflow** by adding a step to `.github/workflows/outreach.yml`
5. **Add to dashboard** by adding an entry to `CAMPAIGN_COLLECTIONS` in `cloudflare/functions/api/stats.js`

See `docs/campaigns.md` for detailed instructions.

---

## Example: Custom Campaign (`my_campaign`)

**Target:** [Describe your target audience and language]
**Language:** [e.g. French, German, Hebrew, Spanish]
**Sequence:** Initial + Follow-up 1 + Follow-up 2 (breakup)

---

### Initial Email

**Subject:** [Your subject line — in target language]

[Greeting] {contact_name},

[Opening — who you are and why you're writing. 2-3 sentences.]

[What you offer and why it's relevant to {org_name}. 3-4 sentences.]

[Key benefits — use bullet points if helpful:]
- [Benefit 1]
- [Benefit 2]
- [Benefit 3]

[Link to more information or a demo]

[Your name]
[Your Org] | [your website]
[phone] | [email]

---

### Follow-up 1 (Day 3)

**Subject:** Re: [Original subject] — {org_name}

[Greeting] {contact_name},

[Brief follow-up — confirm the previous email arrived. 1 sentence.]

[Restate the core offer in one sentence. Include the link again.]

[Your name] | [Your Org] | [your website]

---

### Follow-up 2 (Day 7 — breakup)

**Subject:** Re: [Original subject] — {org_name}

[Greeting] {contact_name},

[Last message — keep it gracious and brief. 2-3 sentences.]

[If {org_name} might be relevant in the future, the door is open.]

[Your name] | [email] | [website]

---

## Code snippet — adding to step6_send_emails.py

In the `build_email()` function, add:

```python
elif tier == "my_campaign":
    name = contact.get("contact_name") or ""
    if email_type == "initial":
        return (
            f"[Subject for {org_short}]",
            f"""[Greeting] {name},

[Your email body here.]

{SIG_FULL}"""
        )
    elif email_type == "followup1":
        return (
            f"Re: [Subject] — {org_short}",
            f"""[Greeting] {name},

[Follow-up body.]

{SIG_SLIM}"""
        )
    elif email_type == "followup2":
        return (
            f"Re: [Subject] — {org_short}",
            f"""[Greeting] {name},

[Breakup email body.]

{SIG_SLIM}"""
        )
    else:
        return None, None
```

For RTL languages (Hebrew, Arabic), pass `rtl=True` to `send_email()` in `send_initial_emails()` and `send_followups()`.
