
bl_info = {
    "name": "Add-on for FrontISTR",
    "author": "Takuya Matsunaga",
    "version": (0, 0, 8),
    "blender": (4, 2, 0),
    "location": "File > Import > FrontISTR",
    "description": "Import and visualize FrontISTR files",
    "warning": "",
    "doc_url": "",
    "category": "Import",
}


# make additonal site-packages directory and install required packages there (optional)
if True: # True | False
    required_packages = ["vtk"]
    import os,sys,importlib,subprocess
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sitepackages_dir = os.path.join(current_dir,"site-packages")
    if not os.path.exists(sitepackages_dir):
        os.makedirs(sitepackages_dir)
    if not sitepackages_dir in sys.path:
        sys.path = [sitepackages_dir] + sys.path
    for package in required_packages:
        try:
            importlib.import_module(package)
        except ImportError:
            print(f"Installing {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package, "--target", sitepackages_dir])
    # workaround for vtk import error on linux and mac
    if os.name == "posix":
        filepath0 = os.path.join(sitepackages_dir,"vtk.py")
        filepath1 = os.path.join(sitepackages_dir,"vtk_bak.py")
        if not "blender-addon-for-frontistr" in open(filepath0).read():
            print(f"Resolving vtk import error...")
            with open(filepath0,"r") as f0, open(filepath1,"w") as f1:
                f1.write(f0.read())
            with open(filepath0,"w") as f0, open(filepath1,"r") as f1:
                for line in f1:
                    if "from vtkmodules.vtkRenderingMatplotlib import *" in line:
                        f0.write("# Commented out for workaround for VTK import error on linux by blender-addon-for-frontistr\n")
                        f0.write("# "+line)
                    else:
                        f0.write(line)


if "bpy" in locals():
    import importlib
    importlib.reload(import_vtu)
    importlib.reload(import_vtu_sequence)
else:
    import bpy
    from . import import_vtu
    from . import import_vtu_sequence

def register():
    import_vtu.register()
    import_vtu_sequence.register()

def unregister():
    import_vtu.unregister()
    import_vtu_sequence.unregister()

if __name__ == "__main__":
    register()
