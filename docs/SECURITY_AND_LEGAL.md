# Security and legal considerations

> **This is not legal advice.** I'm not a lawyer. Everything here is a list of things to *ask* your attorney about, or to be aware of. Where I state something about the law, treat it as "verify this."

## 1. Act on these first

1. **The public info page shows the ICU door code and room number.** `~/dev/active/travis/index.html` publishes "12789 #", "Pedersen Tower, Room 424", and the hospital. Anyone with the URL can read it, including the driver's side, curious strangers, or worse. GitHub Pages also keeps old versions in git history, so removing it later doesn't erase it. Consider:
   - moving the door code and room behind this app's login;
   - asking the hospital whether the code can be rotated.
2. **The info page also says "We suspect the driver was drunk."** A news article says an intoxicated driver was arrested, so this may be accurate. But it's still a public statement by the family about the other party, and it's discoverable. Ask the attorney to review the wording, and get their guidance before posting anything further about the driver, the crash, or fault (on the page, in the journal, or on social media).
3. **Snapshot what exists now** and don't delete it: the Google Sheet (export it), and the GitHub Pages repo history. See "Preservation" below.
4. **Talk to the attorney before launch** about the journal, using the questions in section 6.

## 2. The journal is probably discoverable

The other side, and the insurer, can generally request relevant records. Assume that everything written here, and the photos, could be read by them and shown to a jury. Unless your attorney says otherwise, it isn't protected as attorney-client communication. (Ask whether keeping it "at the attorney's direction" changes that. Some lawyers prefer it that way.)

What that means for what people write:

- **Write what you saw.** "Bruise on left forearm about the size of a fist, purple and yellow." Not "the driver did this to him."
- **If someone told you, say who.** "Nurse [name] said the MRI showed..." Secondhand accounts are still useful, but they need a named source.
- **No speculation about fault, drinking, or blame.** Leave that to the lawyers.
- **No exaggeration, and no jokes.** A defense lawyer reads these entries looking for inconsistency. "He seemed totally fine today, we were laughing" next to a 9/10 pain rating gets used against him.
- **Record good days as well as bad ones.** Honest, consistent records are more credible than one-sided ones. Recovery isn't a straight line, and that's fine.
- **Don't put in** insurance policy numbers, SSN, birthdates, or account numbers.
- **Medical details are what you were told, not the record.** If a note paraphrases an MRI result or a diagnosis, a mismatch with the actual medical chart later can be used to question the journal's reliability generally, not just that one entry. Keep it to "the nurse said..." rather than stating it as fact, and don't worry about getting clinical terms exactly right — that's what the medical record is for.

The questionnaire in the app carries this guidance as short reminders. Every visitor sees it at the start.

## 3. Preservation (don't delete, don't rewrite)

Once a lawsuit or claim is reasonably expected, deleting or altering relevant records can be treated as **spoliation**, and courts can penalize it even if it was innocent. In practice:

- The app is **append-only by design**. Entries can be corrected for 24 hours by their author. After that, only addenda ("correction: I said left, it was right"). Every edit is kept as a revision. Photos can't be deleted by visitors. Admin deletions are soft, need a reason, and are logged.
- **Don't clean up** the old page, the Google Sheet, group chats, texts or photos on phones. Keep them.
- Keep records until the attorney says the matter is completely resolved. Don't purge anything on a schedule.
- If someone asks to remove *their own* entry or photo, don't just do it. Ask the attorney first.

## 4. Making the evidence believable

Photos and notes are usually authenticated by the person who made them saying "yes, I took this, and it shows what it looked like that day." So:

| What the app does | Why |
|---|---|
| Requires each visitor's **full name** | So there's a named witness for each photo and note. |
| Records **server timestamps** that users can't change | Independent of anyone's phone clock. Keep the server's time sync (NTP) on. |
| Keeps the **original photo file byte-for-byte**, including EXIF (capture time, device) | The original is the strongest form. The app's display copies are separate and never replace it. |
| Stores a **SHA-256 hash** of each original | Lets you show a file hasn't changed since upload. |
| Keeps an **audit log** of admin actions, exports and edits | Shows who did what, and when. |
| Export includes a **manifest** listing every file and hash | Something concrete to hand the lawyer. |

Ask the attorney what they want in an export, since the format may matter. It's cheap to add later. Also ask whether people who took photos should write a short signed statement now, while memory is fresh.

Tip for photographers: the app records timestamps, so you don't need to write dates into the frame. Take a couple of consistent shots per injury each visit (same area, similar distance, similar lighting) so progress comparisons are meaningful.

## 5. Privacy, consent and hospital rules

- **Travis's consent.** It's his medical information and his case. While he can't decide, ask the attorney and family who has authority (healthcare proxy or power of attorney). As soon as he's able, tell him about this and let him direct it, including what photos are taken.
- **Photos in the hospital.** Ask the charge nurse about the ICU's photo policy. Don't capture other patients, visitors or staff. Crop or retake if someone appears in the background. Don't upload a photo that shows another patient.
- **Audio/video recording.** I believe Utah is generally a one-party-consent state for recording conversations, but hospitals have their own rules, and staff may object. Verify before recording any conversation with staff, and don't do it covertly.
- **HIPAA.** It applies to hospitals, insurers and their contractors. It generally doesn't bind family members keeping notes. This is still sensitive health data, so the app minimizes what it keeps and restricts access.
- **Visitor access.** Visitors see the calendar (names and times) and **only their own entries**. Only family/admin accounts see everything. This is deliberate. Independent, uncoordinated recollections are more credible than notes that people have read and echoed.

## 6. Questions for the attorney

Bring this list.

- Is the journal fine as designed? Should it be kept at your direction, and does that change what's protected?
- What format do you want records in? Should photographers sign statements?
- What are the **deadlines**? Statute of limitations, notice deadlines in the family's own insurance policies, and any claim deadlines under Utah's auto no-fault rules (PIP) or uninsured/underinsured coverage (UM/UIM). (Don't rely on anything I might remember here. Get the actual dates.)
- Can we keep posting updates on the public page? What should and shouldn't be said, especially about the driver?
- Is it OK to photograph in the ICU, and to record medical staff?
- Who has authority for Travis while he's incapacitated?
- How long do we retain everything, and what happens to it at the end?
- Should we tell the insurance companies about the journal, or wait to be asked?

## 7. Security threat model for the app

| Risk | What the app does about it |
|---|---|
| **The invite link gets forwarded** to people who shouldn't have it | Long random token. Admin can rotate or revoke it at any time. Each visitor gets their own identity, so an admin can revoke one person. `join` is rate-limited. |
| A stranger guesses or scrapes photo URLs | Photos are never public. Each request is checked (401 if not logged in, 403 if it isn't yours). Downloads go through Django, not a public folder. |
| Someone uploads something malicious | JPEG/PNG/HEIC/WebP only, verified by actually decoding, not by trusting the filename or content type. SVG rejected. Size limited. |
| Visitor edits history | 24-hour edit window, then addenda only. Revisions and the audit log are kept. |
| The server is compromised or lost | Encrypted off-server backups, tested. Firewall, key-only SSH, updates. Secrets in the encrypted keychain. |
| Search engines or bots index it | `noindex`, `robots.txt`, no third-party scripts. |
| Someone impersonates a visitor on a new device | Re-joining creates a new identity, and admin can merge or flag duplicates. Attribution stays honest. |

Not in v1: two-factor auth for family accounts, email/SMS alerts, and an approval queue for new joiners. All are easy to add if the link leaks.
