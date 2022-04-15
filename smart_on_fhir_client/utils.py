from typing import Dict, Any, Mapping

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from jwt import DecodeError
from jwt.algorithms import RSAAlgorithm


def mixin(cls):
    return cls


def check_id_token(
    id_token: str,
    *,
    key: str | Mapping | RSAPrivateKey | RSAPublicKey,
    issuer: str,
    audience: str,
) -> Dict[str, Any]:
    # see google
    if isinstance(key, (str, Mapping)):
        public_key = RSAAlgorithm.from_jwk(key)
    else:
        public_key = key
    opts = dict(verify_exp=True, verify_aud=True)
    try:
        payload = jwt.decode(
            id_token,
            key=public_key,
            algorithms=["RS256"],
            options=opts,
            issuer=issuer,
            audience=audience,
        )
    except:
        raise DecodeError("Error decoding jwt token")
    else:
        return payload
