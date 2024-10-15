
import bpy
import bpy_extras
import os
import numpy
import pathlib
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from .import_vtu import (
    VtuData,
    ATTRIBUTE_NAME_DISPLACEMENT,
    ATTRIBUTE_NAME_MISES_STRESS,
    new_geometry_nodes,
    new_material_nodes
)


def fistr_import_vtu_sequence(self, context):
    import time as timer
    t0 = timer.perf_counter()
    
    filepaths = [os.path.join(self.directory, file.name) for file in self.files]
    nfiles = len(filepaths)
    if nfiles == 0:
        self.report({'ERROR'}, "No files selected")
        return {'CANCELLED'}
    
    frame_start = 1
    frame_end = nfiles
    
    objname = bpy.path.display_name_from_filepath(filepaths[0])
    objname = objname.replace(".","_")+f"_{nfiles}"
    print(f"objname = {objname}")
    
    # load vtu file and extract surface
    vtu = VtuData(filepaths[0])
    vtu_surface = vtu.extract_surface()
    npoints = vtu_surface.npoints()
    ncells = vtu_surface.ncells()
    cellsize = numpy.cbrt(vtu.calc_cell_volumes().mean())
    connectivity = vtu_surface.cells_connectivity()
    offsets = vtu_surface.cells_offsets()
    
    # Create mesh
    mesh_verts = vtu_surface.points()
    mesh_faces = [tuple(connectivity[offsets[i]:offsets[i+1]]) for i in range(ncells)]
    mesh = bpy.data.meshes.new(name=f"{objname}.mesh")
    mesh.from_pydata(mesh_verts,[],mesh_faces)
    mesh.update()
    
    # Create object
    obj = bpy_extras.object_utils.object_data_add(context, mesh, name=f"{objname}")
    
    # Set object properties
    obj.location = (0,0,0)
    obj.scale = (1,1,1)
    
    # Set object attributes
    mises_stress_min = 0.0
    mises_stress_max = 0.0
    for i,filepath in enumerate(filepaths):
        warnings = []
        frame = frame_start+i
        current_vtu_surface = VtuData(filepaths[i]).extract_surface()
        attr_displacement = current_vtu_surface.point_attribute_array(ATTRIBUTE_NAME_DISPLACEMENT)
        if attr_displacement is None:
            warnings.append("Displacement array not found")
        elif attr_displacement.shape != (npoints,3):
            warnings.append(f"Displacement array shape mismatch: {attr_displacement.shape} instead of {(npoints,3)}")
        else:
            obj.data.attributes.new(name=f"{frame}/{ATTRIBUTE_NAME_DISPLACEMENT}",type='FLOAT_VECTOR',domain='POINT')
            obj.data.attributes[f"{frame}/{ATTRIBUTE_NAME_DISPLACEMENT}"].data.foreach_set("vector", attr_displacement.flatten())
        attr_mises_stress = current_vtu_surface.point_attribute_array(ATTRIBUTE_NAME_MISES_STRESS)
        if attr_mises_stress is None:
            warnings.append("Mises stress array not found")
        elif attr_mises_stress.shape != (npoints,):
            warnings.append(f"Mises stress array shape mismatch: {attr_mises_stress.shape} instead of {(npoints,)}")
        else:
            obj.data.attributes.new(name=f"{frame}/{ATTRIBUTE_NAME_MISES_STRESS}",type='FLOAT',domain='POINT')
            obj.data.attributes[f"{frame}/{ATTRIBUTE_NAME_MISES_STRESS}"].data.foreach_set("value", attr_mises_stress)
            mises_stress_min = min(mises_stress_min,attr_mises_stress.min())
            mises_stress_max = max(mises_stress_max,attr_mises_stress.max())
        if warnings:
            message = ""
            message += f"filepaths[{i}] = {filepath!r}\\n"
            for warning in warnings:
                message += f"  - {warning}\\n"
            self.report({'WARNING'},message)
    
    # Create material for surface
    material1,matnodes1 = new_material_nodes(context, obj, f"{objname}.material")
    
    node_p_BSDF = matnodes1.nodes[bpy.app.translations.pgettext_data("Principled BSDF")]
    node_output = matnodes1.nodes[bpy.app.translations.pgettext_data("Material Output")]
    
    node_inputattr = matnodes1.nodes.new(type="ShaderNodeAttribute")
    node_inputattr.attribute_name = "color_factor"
    node_inputattr.width = 240
    
    node_toRGB = matnodes1.nodes.new(type="ShaderNodeValToRGB")
    node_toRGB.color_ramp.color_mode = "HSL"
    node_toRGB.color_ramp.hue_interpolation = "FAR"
    node_toRGB.color_ramp.elements[0].color = (0,0,1,1)
    node_toRGB.color_ramp.elements[1].color = (1,0,0,1)
    node_toRGB.location.x = node_inputattr.location.x+node_inputattr.width+40
    node_toRGB.location.y = node_inputattr.location.y
    matnodes1.links.new(node_inputattr.outputs["Fac"], node_toRGB.inputs["Fac"])
    
    node_p_BSDF.inputs[1].default_value = 0.0 # Metallic
    node_p_BSDF.inputs[2].default_value = 1.0 # Roughness
    node_p_BSDF.inputs[3].default_value = 1.0 # IOR
    node_p_BSDF.inputs[4].default_value = 1.0 # Alpha
    node_p_BSDF.inputs[7].default_value = 0.0 # Subsurface/Weight
    node_p_BSDF.inputs[8].default_value = (1.0,1.0,1.0) # Subsurface/Radius
    node_p_BSDF.inputs[9].default_value = cellsize*0.05 # Subsurface/Scale[m]
    node_p_BSDF.location.x = node_toRGB.location.x+node_toRGB.width+40
    node_p_BSDF.location.y = node_toRGB.location.y
    matnodes1.links.new(node_toRGB.outputs["Color"], node_p_BSDF.inputs["Base Color"])
    
    node_output.location.x = node_p_BSDF.location.x+node_p_BSDF.width+40
    node_output.location.y = node_p_BSDF.location.y
    
    # Create material for wireframe
    material2,matnodes2 = new_material_nodes(context, obj, f"{objname}.wireframe.material")
    
    node_p_BSDF = matnodes2.nodes[bpy.app.translations.pgettext_data("Principled BSDF")]
    node_output = matnodes2.nodes[bpy.app.translations.pgettext_data("Material Output")]
    
    node_p_BSDF.inputs[0].default_value = (1.0,1.0,1.0,1.0) # Base Color
    node_p_BSDF.inputs[1].default_value = 0.0 # Metallic
    node_p_BSDF.inputs[2].default_value = 1.0 # Roughness
    node_p_BSDF.inputs[3].default_value = 1.0 # IOR
    node_p_BSDF.inputs[4].default_value = 1.0 # Alpha
    node_p_BSDF.inputs[7].default_value = 0.0 # Subsurface/Weight
    node_p_BSDF.inputs[8].default_value = (1.0,1.0,1.0) # Subsurface/Radius
    node_p_BSDF.inputs[9].default_value = cellsize*0.05 # Subsurface/Scale[m]
    
    # Create geometry nodes
    geonodes = new_geometry_nodes(context, obj, f"{objname}.geonodes")
    
    node_input = geonodes.nodes[bpy.app.translations.pgettext_data("Group Input")]
    node_output = geonodes.nodes[bpy.app.translations.pgettext_data("Group Output")]
    
    node_scenetime = geonodes.nodes.new(type="GeometryNodeInputSceneTime")
    node_scenetime.location.x = node_input.location.x-900
    node_scenetime.location.y = node_input.location.y-100
    
    node_clamp = geonodes.nodes.new(type="ShaderNodeClamp")
    node_clamp.inputs[1].default_value = frame_start
    node_clamp.inputs[2].default_value = frame_end
    node_clamp.location.x = node_scenetime.location.x+node_scenetime.width+40
    node_clamp.location.y = node_scenetime.location.y
    geonodes.links.new(node_scenetime.outputs[1], node_clamp.inputs[0])
    
    node_valuetostring = geonodes.nodes.new(type="FunctionNodeValueToString")
    node_valuetostring.inputs[1].default_value = 0
    node_valuetostring.location.x = node_clamp.location.x+node_clamp.width+40
    node_valuetostring.location.y = node_clamp.location.y
    geonodes.links.new(node_clamp.outputs[0], node_valuetostring.inputs[0])
    
    node_inputstring1 = geonodes.nodes.new(type="FunctionNodeInputString")
    node_inputstring1.string = ATTRIBUTE_NAME_DISPLACEMENT
    node_inputstring1.location.x = node_valuetostring.location.x
    node_inputstring1.location.y = node_valuetostring.location.y-node_valuetostring.height-50
    
    node_inputstring2 = geonodes.nodes.new(type="FunctionNodeInputString")
    node_inputstring2.string = ATTRIBUTE_NAME_MISES_STRESS
    node_inputstring2.location.x = node_inputstring1.location.x
    node_inputstring2.location.y = node_inputstring1.location.y-node_inputstring1.height-50
    
    node_joinstrings1 = geonodes.nodes.new(type="GeometryNodeStringJoin")
    node_joinstrings1.inputs[0].default_value = "/"
    node_joinstrings1.location.x = node_inputstring1.location.x+node_inputstring1.width+40
    node_joinstrings1.location.y = node_inputstring1.location.y+50
    geonodes.links.new(node_inputstring1.outputs[0], node_joinstrings1.inputs[1])
    geonodes.links.new(node_valuetostring.outputs[0], node_joinstrings1.inputs[1])
    
    node_joinstrings2 = geonodes.nodes.new(type="GeometryNodeStringJoin")
    node_joinstrings2.inputs[0].default_value = "/"
    node_joinstrings2.location.x = node_inputstring2.location.x+node_inputstring2.width+40
    node_joinstrings2.location.y = node_inputstring2.location.y+50
    geonodes.links.new(node_inputstring2.outputs[0], node_joinstrings2.inputs[1])
    geonodes.links.new(node_valuetostring.outputs[0], node_joinstrings2.inputs[1])
    
    node_inputattr1 = geonodes.nodes.new(type="GeometryNodeInputNamedAttribute")
    node_inputattr1.data_type = 'FLOAT_VECTOR'
    node_inputattr1.location.x = node_joinstrings1.location.x+node_joinstrings1.width+40
    node_inputattr1.location.y = node_joinstrings1.location.y
    geonodes.links.new(node_joinstrings1.outputs[0], node_inputattr1.inputs[0])
    
    node_inputattr2 = geonodes.nodes.new(type="GeometryNodeInputNamedAttribute")
    node_inputattr2.data_type = 'FLOAT'
    node_inputattr2.location.x = node_joinstrings2.location.x+node_joinstrings2.width+40
    node_inputattr2.location.y = node_joinstrings2.location.y
    geonodes.links.new(node_joinstrings2.outputs[0], node_inputattr2.inputs[0])
    
    node_scale = geonodes.nodes.new(type="ShaderNodeVectorMath")
    node_scale.operation = 'SCALE'
    node_scale.inputs[3].default_value = 1
    node_scale.location.x = node_inputattr1.location.x+node_inputattr1.width+40
    node_scale.location.y = node_inputattr1.location.y
    geonodes.links.new(node_inputattr1.outputs[0], node_scale.inputs[0])
    
    node_setposition = geonodes.nodes.new(type="GeometryNodeSetPosition")
    node_setposition.location.x = node_input.location.x+node_input.width+40
    node_setposition.location.y = node_input.location.y
    geonodes.links.new(node_input.outputs[0], node_setposition.inputs[0])
    geonodes.links.new(node_scale.outputs[0], node_setposition.inputs[3])
    
    node_maprange2 = geonodes.nodes.new(type="ShaderNodeMapRange")
    node_maprange2.inputs[1].default_value = mises_stress_min # From Min
    node_maprange2.inputs[2].default_value = mises_stress_max # From Max
    node_maprange2.inputs[3].default_value = 0.0 # To Min
    node_maprange2.inputs[4].default_value = 1.0 # To Max
    node_maprange2.location.x = node_inputattr2.location.x+node_inputattr2.width+40
    node_maprange2.location.y = node_inputattr2.location.y
    geonodes.links.new(node_inputattr2.outputs[0], node_maprange2.inputs[0])
    
    node_storeattr2 = geonodes.nodes.new(type="GeometryNodeStoreNamedAttribute")
    node_storeattr2.data_type = "FLOAT"
    node_storeattr2.domain = "POINT"
    node_storeattr2.inputs[2].default_value = "color_factor"
    node_storeattr2.location.x = node_setposition.location.x+node_setposition.width+40
    node_storeattr2.location.y = node_setposition.location.y
    node_storeattr2.width = 260
    geonodes.links.new(node_setposition.outputs[0], node_storeattr2.inputs[0])
    geonodes.links.new(node_maprange2.outputs[0], node_storeattr2.inputs[3])
    
    node_meshtocurve = geonodes.nodes.new(type="GeometryNodeMeshToCurve")
    node_meshtocurve.location.x = node_storeattr2.location.x+node_storeattr2.width+40
    node_meshtocurve.location.y = node_storeattr2.location.y-node_storeattr2.height-40
    geonodes.links.new(node_storeattr2.outputs[0], node_meshtocurve.inputs[0])
    
    node_curvecircle = geonodes.nodes.new(type="GeometryNodeCurvePrimitiveCircle")
    node_curvecircle.mode = "RADIUS"
    node_curvecircle.inputs[0].default_value = 32 # Resolution
    node_curvecircle.inputs[4].default_value = cellsize*0.01 # Radius [m]
    node_curvecircle.location.x = node_meshtocurve.location.x
    node_curvecircle.location.y = node_meshtocurve.location.y-node_meshtocurve.height-20
    
    node_curvetomesh = geonodes.nodes.new(type="GeometryNodeCurveToMesh")
    node_curvetomesh.location.x = node_meshtocurve.location.x+node_meshtocurve.width+40
    node_curvetomesh.location.y = node_meshtocurve.location.y
    geonodes.links.new(node_meshtocurve.outputs[0], node_curvetomesh.inputs[0])
    geonodes.links.new(node_curvecircle.outputs[0], node_curvetomesh.inputs[1])
    
    node_setmaterial1 = geonodes.nodes.new(type="GeometryNodeSetMaterial")
    node_setmaterial1.inputs[2].default_value = material1
    node_setmaterial1.location.x = node_curvetomesh.location.x+node_curvetomesh.width+40
    node_setmaterial1.location.y = node_storeattr2.location.y
    geonodes.links.new(node_storeattr2.outputs[0], node_setmaterial1.inputs[0])
    
    node_setmaterial2 = geonodes.nodes.new(type="GeometryNodeSetMaterial")
    node_setmaterial2.inputs[2].default_value = material2
    node_setmaterial2.location.x = node_curvetomesh.location.x+node_curvetomesh.width+40
    node_setmaterial2.location.y = node_curvetomesh.location.y
    geonodes.links.new(node_curvetomesh.outputs[0], node_setmaterial2.inputs[0])
    
    node_joingeometry = geonodes.nodes.new(type="GeometryNodeJoinGeometry")
    node_joingeometry.location.x = node_setmaterial1.location.x+node_setmaterial1.width+40
    node_joingeometry.location.y = node_setmaterial1.location.y
    geonodes.links.new(node_setmaterial2.outputs[0], node_joingeometry.inputs[0])
    geonodes.links.new(node_setmaterial1.outputs[0], node_joingeometry.inputs[0])
    
    node_output.location.x = node_joingeometry.location.x+node_joingeometry.width+40
    node_output.location.y = node_joingeometry.location.y
    geonodes.links.new(node_joingeometry.outputs[0], node_output.inputs[0])
    
    # finish
    t1 = timer.perf_counter()
    print(f"Successfully imported {nfiles} files in {t1-t0:.3f} sec")
    
    # Select created object
    obj.select_set(True)
    
    return {'FINISHED'}


class FISTR_ImportVtuSquence(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "fistr.import_vtu_sequence"
    bl_label = "Import VTU files"
    bl_options = {'REGISTER','UNDO'}

    filter_glob: bpy.props.StringProperty(default="*.vtu;*.pvtu", options={'HIDDEN'})
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN','SKIP_SAVE'})

    def execute(self, context):
        return fistr_import_vtu_sequence(self, context)


def menu_func_import(self, context):
    self.layout.operator(FISTR_ImportVtuSquence.bl_idname, text="FrontISTR VTU sequence (.vtu|.pvtu)")

def register():
	bpy.utils.register_class(FISTR_ImportVtuSquence)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(FISTR_ImportVtuSquence)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
