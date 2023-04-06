import numpy as np
from simulation_function import makeSimulation

# make simulaiton class and save data directory
simul = makeSimulation("Result")

# Set transducer spec
simul.source_freq = 25e4
simul.ROC = 99
simul.width = 95
simul.focal_length = 85

# Set sonication condition
simul.end_time = 100e-6
simul.points_per_wavelength = np.pi*2
simul.CFL = 0.1

# Set target location // Thalamus
target = [-15.538, 7.803, 22.017]

# Set Simulation ROI
simul.preprocessing('Test Data\\Skull.nii', target)

# Find optimal placement of the transducer using Time-reversal simulation
simul.findOptimalPosition()

# Optimal placement assign
tran_pos = simul.optimalPos
tran_normal = simul.optialNormal

# Make transducer using optimized transducer placement
simul.make_transducer(tran_pos, tran_normal)

# Run Forward simulation
simul.run_simulation()

