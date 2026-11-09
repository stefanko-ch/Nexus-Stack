# OpenBao server configuration (bao server -config=/openbao/config/bao.hcl).

ui           = true
api_addr     = "http://openbao:8200"
cluster_addr = "http://openbao:8201"

# Integrated (Raft) storage, a single node. OpenBao 2 no longer has the
# plain file backend.
storage "raft" {
  path    = "/openbao/file"
  node_id = "nexus-openbao"
}

# Plain HTTP inside the stack; Cloudflare terminates TLS in front of the UI.
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

# Auto-unseal with a static AES-256 key generated per deployment (Infisical
# folder `openbao`, OPENBAO_UNSEAL_KEY). Without it the server would come up
# sealed after every restart and wait for someone to type unseal keys.
seal "static" {
  current_key_id = "nexus-1"
  current_key    = "env://OPENBAO_UNSEAL_KEY"
}
