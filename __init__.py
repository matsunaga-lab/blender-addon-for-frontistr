
bl_info = {
    "name": "Add-on for FrontISTR",
    "author": "Takuya Matsunaga",
    "version": (0, 0, 4),
    "blender": (4, 2, 0),
    "location": "File > Import > FrontISTR",
    "description": "Import and visualize FrontISTR files",
    "warning": "",
    "doc_url": "",
    "category": "Import",
}

required_modules = ["vtk"]

# install required modules
if True: # True | False
	import importlib,subprocess,sys
	for module in required_modules:
		try:
			importlib.import_module(module)
		except ImportError:
			subprocess.run([sys.executable, "-m", "pip", "install", module])

# workaround for vtk import error on linux and mac
if True: # True | False
    import os
    if os.name == "posix":
        import site
        for dir in site.getsitepackages():
            filepath0 = os.path.join(dir,"vtk.py")
            filepath1 = os.path.join(dir,"vtk_for_fistr.py")
            if not os.path.isfile(filepath0):
                continue
            with open(filepath0,"r") as f0, open(filepath1,"w") as f1:
                for line in f0:
                    if "from vtkmodules.vtkRenderingMatplotlib import *" in line:
                        f1.write("# "+line)
                    else:
                        f1.write(line)

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
