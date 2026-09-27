"""A signed file listing must never authorize reads outside the bundle tree."""

import hashlib
import json

import pytest

from contracts.karmi_reference import loader as karmi
from model_lab.artifacts import bundle, signer


@pytest.mark.parametrize("kind", ["traversal", "symlink"])
def test_signed_bundle_rejects_external_file_references(tmp_path, kind):
    key = signer.generate_key(tmp_path / "key.hex")
    secret = signer.load_private(tmp_path / "key.hex")
    root = tmp_path / "bundle"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"external":true}')
    name = "../outside.json" if kind == "traversal" else "payload.json"
    if kind == "symlink":
        (root / name).symlink_to(outside)
    checksums = json.dumps({"algorithm": "sha256", "files": {
        name: hashlib.sha256(outside.read_bytes()).hexdigest()}}, sort_keys=True).encode()
    (root / "checksums.json").write_bytes(checksums)
    (root / "signature.sig").write_text(json.dumps(signer.sign(secret, checksums, signed_file="checksums.json")))
    assert bundle.verify(root, [key["public_key"]])
    with pytest.raises(karmi.BundleRejected):
        karmi.load_bundle(root, trusted_public_keys=[key["public_key"]], karmi_version="0.1.0",
                          known_actions=["sim/cheap"], expected_feature_schema_version="routing-features.v1")
