"""Public keys whose signatures this product accepts on licence files (Ed25519, raw, base64url).

Only public keys belong here. The matching private key is the vendor's and must never be committed or copied to a
customer server. To rotate: generate a new pair with `manage.py licence_keygen`, add the new public key here
(keep the old one until every customer has a licence signed with the new key), release, then remove the old one.
"""

TRUSTED_PUBLIC_KEYS = [
    "gsIiK8kDoTyhaqCg8ikvqmJe34akG7UNehNOz4TIkts",          # ShineLight vendor key, 2026-10
]
