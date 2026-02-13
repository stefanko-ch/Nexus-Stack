## LakeFS

![LakeFS](https://img.shields.io/badge/LakeFS-00B4D8?logo=git&logoColor=white)

**Git-like version control for data lakes**

LakeFS provides Git-like version control for data stored in object storage. Features include:
- Branch, commit, merge, and diff for data
- S3-compatible gateway for transparent access
- Built-in web UI for repository management
- Zero-copy branching (no data duplication)
- Automatic repository creation based on backend type

| Setting | Value |
|---------|-------|
| Default Port | `8000` (Web UI + API + S3 Gateway) |
| Suggested Subdomain | `lakefs` |
| Public Access | No (data management) |
| Website | [lakefs.io](https://lakefs.io) |
| Source | [GitHub](https://github.com/treeverse/lakeFS) |

> **Note:** LakeFS is a version control layer for object storage. It can use **Hetzner Object Storage** (recommended for production) or **local filesystem** (development/testing).

### Storage Backend Configuration

**Option 1: Hetzner Object Storage (Recommended for Production)**

1. Create S3 credentials in [Hetzner Cloud Console](https://console.hetzner.cloud):
   - Navigate to **Storage** → **Object Storage** → **S3 Credentials**
   - Generate new credentials and save the **Access Key** and **Secret Key**

2. Add to **GitHub Secrets**:
   ```
   HETZNER_OBJECT_STORAGE_ACCESS_KEY = <your-access-key>
   HETZNER_OBJECT_STORAGE_SECRET_KEY = <your-secret-key>
   ```

3. Deploy - LakeFS automatically configures Hetzner S3 as backend

**Option 2: Local Filesystem (Automatic Fallback)**

If Hetzner Object Storage credentials are not configured, LakeFS automatically falls back to local filesystem storage. No additional configuration needed, but:
- ⚠️ Data is stored on server disk
- ⚠️ Data is lost on teardown
- ✅ Suitable for development/testing

**What's Automated:**
- Bucket creation (if using Hetzner S3)
- LakeFS admin user creation
- Default repository creation (`hetzner-object-storage` for S3, `local-storage` for local)
- Backend configuration (S3 or local filesystem)

### Architecture

| Container | Purpose |
|-----------|---------|
| `lakefs` | Web UI + API server + S3 gateway |
| `lakefs-db` | Dedicated PostgreSQL for metadata |

### Access Methods

LakeFS uses a **single port (8000)** for all services, but separates them via DNS:

**1. Web UI (via Cloudflare Tunnel):**
- URL: `https://lakefs.<domain>`
- Access: Protected by Cloudflare Access (email OTP)
- Use for: Browser-based repository management

**2. S3 Gateway (direct TCP access):**
- URL: `s3://s3.lakefs.<domain>:8000` or `http://s3.lakefs.<domain>:8000`
- Access: Direct server connection (requires firewall rule enabled in Control Plane)
- Use for: External tools (Databricks, Spark, DuckDB, Python boto3)

LakeFS routes requests based on the `Host` header:
- `lakefs.<domain>` → Web UI/API
- `s3.lakefs.<domain>` → S3 Gateway

### Usage

**Web UI Setup:**
1. Access LakeFS at `https://lakefs.<domain>`
2. On first launch, create an admin user via the setup wizard
3. Create a repository pointing to the auto-created bucket
4. Use branches for data experimentation, merge when ready

**S3 Gateway Access (requires firewall rule):**
```python
# Python example with boto3
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://s3.lakefs.your-domain.com:8000',
    aws_access_key_id='<your-lakefs-access-key>',
    aws_secret_access_key='<your-lakefs-secret-key>'
)

# List repositories
s3.list_buckets()
```
