# Windows: double-click to start RealSampleCalibration without a console window.
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "RealSampleCalibration.py"), run_name="__main__")
