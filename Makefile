.PHONY: install test demo regression poisoned late impact
install:
	python -m pip install -e .
test:
	python -m unittest discover -s tests -v
demo:
	python -m medallion_x.cli demo --scenario clean --out-dir runs/clean
regression:
	python -m medallion_x.cli demo --scenario regression --expect-block --out-dir runs/regression
poisoned:
	python -m medallion_x.cli demo --scenario poisoned --expect-block --out-dir runs/poisoned
late:
	python -m medallion_x.cli demo --scenario late --out-dir runs/late
impact:
	python -m medallion_x.cli impact

# v2 flight-lab (local, no Fabric needed)
flight-clean:
	PYTHONPATH=src python -m medallion_x.cli flight-test --scenario clean --out-dir runs/v2-clean

flight-regression:
	PYTHONPATH=src python -m medallion_x.cli flight-test --scenario regression --expect-block --out-dir runs/v2-regression

stress:
	PYTHONPATH=src python -m medallion_x.cli stress-test --rounds 100 --seed 42 --out runs/metamorphic.json

fabric-plan:
	python fabric/experiments/plan.py --run-id lab01 --out-dir runs/fabric-plan-lab01
