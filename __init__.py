
bl_info = {
    "name": "Add-on for FrontISTR",
    "author": "Takuya Matsunaga",
    "version": (0, 0, 3),
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
