"""Convert a dynamically quantized model's int8 (S8) weights to uint8 (U8) with zero point + 128. Lossless.

    python -m doonview_ml.u8u8 artifacts/<name>/model.int8.onnx

Why: quantize_dynamic(weight_type=QInt8) makes U8S8 MatMulInteger nodes. On x86 CPUs with AVX2/AVX512 but no
VNNI, ONNX Runtime computes U8S8 with VPMADDUBSW, whose 16-bit sums can saturate; U8U8 has no such issue
(https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html). A model checked on a VNNI CPU
(the B200 host, a Ryzen laptop) then gave different labels on a non-VNNI server. Shifting every weight and its
zero point by 128 represents exactly the same real values (w = scale * (q - zp)), so on CPUs where both paths are
exact the outputs are identical.
"""
import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import numpy_helper


def convert(src: Path, dst: Path) -> int:
    model = onnx.load(str(src))
    inits = {i.name: i for i in model.graph.initializer}
    shifted = set()
    for node in model.graph.node:
        if node.op_type != "MatMulInteger" or len(node.input) < 4:
            continue
        for name in (node.input[1], node.input[3]):  # B and its zero point
            if name in shifted or name not in inits:
                continue
            arr = numpy_helper.to_array(inits[name])
            if arr.dtype == np.uint8:
                continue
            if arr.dtype != np.int8:
                raise SystemExit(f"{name}: unexpected dtype {arr.dtype}")
            inits[name].CopyFrom(numpy_helper.from_array((arr.astype(np.int16) + 128).astype(np.uint8), name))
            shifted.add(name)
    onnx.save(model, str(dst))
    return len(shifted)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else path
    print(f"shifted {convert(path, out)} weight/zero-point tensors to uint8 -> {out}")
