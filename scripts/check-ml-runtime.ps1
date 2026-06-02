param(
  [string]$Python = "py",
  [string]$PythonArgs = "-3"
)

$ErrorActionPreference = "Stop"

$code = @'
import importlib

packages = [
    ("pyvrp", "pyvrp"),
    ("ortools", "ortools"),
    ("requests", "requests"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("networkx", "networkx"),
    ("sklearn", "scikit-learn"),
    ("joblib", "joblib"),
    ("torch", "torch"),
]

failures = []
versions = {}

for module_name, label in packages:
    try:
        module = importlib.import_module(module_name)
        versions[label] = getattr(module, "__version__", "unknown")
    except Exception as exc:
        failures.append(f"{label}:{exc.__class__.__name__}:{exc}")

if failures:
    print("IRX_ML_RUNTIME_FAIL")
    for failure in failures:
        print(failure)
    raise SystemExit(1)

torch = importlib.import_module("torch")
print("IRX_ML_RUNTIME_OK")
for key in sorted(versions):
    print(f"{key}={versions[key]}")
print(f"torch_cuda_available={torch.cuda.is_available()}")
print(f"torch_cuda_device_count={torch.cuda.device_count()}")
'@

if ($PythonArgs) {
  $code | & $Python $PythonArgs -
} else {
  $code | & $Python -
}

if ($LASTEXITCODE -ne 0) {
  throw "IRX ML runtime check failed. Run: py -3 -m pip install -r requirements.txt"
}
