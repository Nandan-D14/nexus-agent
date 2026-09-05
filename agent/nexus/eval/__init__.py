# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Production evaluation package.

Owns the 25-task catalog, scorer/report gate, and staging live executor adapter.
Contract mode only validates harness schema. Live baselines must come from a
real staging run and are never invented by the harness.
"""
