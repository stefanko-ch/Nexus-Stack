## Wiki.js

![Wiki.js](https://img.shields.io/badge/Wiki.js-1976D2?logo=wikidotjs&logoColor=white)

**Open-source wiki and knowledge base platform**

Wiki.js is a powerful wiki platform with Markdown editor, visual editor (WYSIWYG), multi-language support, full-text search, and Git-based storage. All content is stored in a dedicated PostgreSQL database and persists across teardown/spin-up cycles.

| Setting | Value |
|---------|-------|
| Default Port | `3005` |
| Suggested Subdomain | `wiki` |
| Public Access | No (Cloudflare Access) |
| Website | [js.wiki](https://js.wiki) |
| Source | [GitHub](https://github.com/Requarks/wiki) |

### Usage

1. Access at `https://wiki.<domain>`
2. Default credentials:
   - Username: `user_email` (from Infisical: `WIKIJS_USERNAME`)
   - Password: From Infisical (`WIKIJS_PASSWORD`)
3. Auto-setup creates the admin account on first deployment
4. Create pages using Markdown or the visual editor
5. Data persists in PostgreSQL across teardown/spin-up cycles

### Data Persistence

Wiki.js stores all content (pages, assets, settings) in the PostgreSQL database. The `wikijs-db-data` Docker volume is mounted to the Hetzner persistent volume, ensuring data survives teardown and spin-up.
