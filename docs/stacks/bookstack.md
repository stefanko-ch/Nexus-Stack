---
title: "BookStack"
---

## BookStack

![BookStack](https://img.shields.io/badge/BookStack-0288D1?logo=bookstack&logoColor=white)

**Documentation wiki organised as shelves, books and pages**

BookStack is a wiki with a fixed structure: shelves hold books, and books hold chapters and pages. It has a WYSIWYG and a Markdown editor, revisions, full-text search, templates, draw.io diagrams and per-page permissions.

| Setting | Value |
|---------|-------|
| Default Port | `8132` (bound to `127.0.0.1` on the host; container port 80) |
| Suggested Subdomain | `bookstack` |
| Public Access | No (protected by Cloudflare Access) |
| Credentials | The stack user's email, password generated per deployment (Infisical folder `bookstack`) |
| Persistence | Docker volumes `bookstack-db` (MariaDB) and `bookstack-config` (uploads, settings) |
| Website | [bookstackapp.com](https://www.bookstackapp.com) |

### BookStack next to the other wikis

[Wiki.js](wikijs.md) is a free-form wiki and [HedgeDoc](hedgedoc.md) is a collaborative Markdown pad. BookStack suits material that should read like a book, such as a course handbook with chapters.

### Login

Sign in with the email shown in Infisical (`BOOKSTACK_EMAIL`, the stack user's) and `BOOKSTACK_PASSWORD`.

The image starts with a default admin, `admin@admin.com` / `password`. On the first start, `nexus-admin.sh` turns that account into yours and checks that the default login no longer works.

If any step fails, the script stops the container instead of letting BookStack run with the default login. The container then restarts, and keeps doing so until the cause is fixed. A failure shows in `docker logs bookstack` as `nexus-admin: ERROR: …`.

The password reaches BookStack's `create-admin` command on stdin, never as a command-line flag.

Tested locally:

- a fresh start, and logging in with the generated password;
- the default login refused;
- a restart, which changes nothing;
- a failure (a password BookStack rejects), which keeps the container from serving.

### Persistence

Content is in MariaDB (`bookstack-db`). Uploads and the BookStack config are in `bookstack-config`.

- **`rebuild` (default): they do not survive a teardown.** BookStack is not in the R2 backup list. Export books (**Export** → contained web file, PDF or Markdown) to keep them.
- **`snapshot`: they survive**, because the whole disk is imaged.
