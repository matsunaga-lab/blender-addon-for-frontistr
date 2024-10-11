
import bpy
import bpy_extras
import os
import numpy
import pathlib
import vtk
from vtk.util.numpy_support import vtk_to_numpy
from vtk.util.numpy_support import numpy_to_vtk


class VtuData:
    def __init__(self,filepath=None):
        self.clear()
        if filepath:
            self.read(filepath)
    def clear(self):
        self.ugrid_ = None
        return self
    def read(self,filepath):
        filepath = pathlib.Path(filepath)
        if filepath.suffix == ".vtu":
            reader = vtk.vtkXMLUnstructuredGridReader()
            reader.SetFileName(filepath)
            reader.Update()
            self.ugrid_ = reader.GetOutput()
        elif filepath.suffix == ".pvtu":
            reader = vtk.vtkXMLPUnstructuredGridReader()
            reader.SetFileName(filepath)
            reader.Update()
            if reader.GetOutput().GetPointData().GetArray("GlobalPointIds") is not None:
                # Merge points based on "GlobalPointIds"
                filter = vtk.vtkStaticCleanUnstructuredGrid()
                filter.SetInputData(reader.GetOutput())
                filter.SetMergingArray("GlobalPointIds")
                filter.Update()
                # Merge duplicate cells
                filter2 = vtk.vtkCleanUnstructuredGridCells()
                filter2.SetInputData(filter.GetOutput())
                filter2.Update()
                self.ugrid_ = filter2.GetOutput()
            elif False:
                # Merge geometrically coincident points
                filter = vtk.vtkCleanUnstructuredGrid()
                filter.SetInputData(reader.GetOutput())
                filter.Update()
                # Merge duplicate cells
                filter2 = vtk.vtkCleanUnstructuredGridCells()
                filter2.SetInputData(filter.GetOutput())
                filter2.Update()
                self.ugrid_ = filter2.GetOutput()
            else:
                self.ugrid_ = reader.GetOutput()
        else:
            raise ValueError(f"Invalid file extension: {filepath.suffix}")
    def npoints(self):
        return self.ugrid_.GetNumberOfPoints()
    def ncells(self):
        return self.ugrid_.GetNumberOfCells()
    def points(self):
        points = self.ugrid_.GetPoints()
        return vtk_to_numpy(points.GetData())
    def cells_connectivity(self):
        cells = self.ugrid_.GetCells()
        return vtk_to_numpy(cells.GetConnectivityArray())
    def cells_offsets(self):
        cells = self.ugrid_.GetCells()
        return vtk_to_numpy(cells.GetOffsetsArray())
    def cells_types(self):
        cells = self.ugrid_.GetCells()
        return vtk_to_numpy(self.ugrid_.GetCellTypesArray())
    def fielddata(self,name=None):
        fielddata = self.ugrid_.GetFieldData()
        ret = {}
        for i in range(fielddata.GetNumberOfArrays()):
            array_i = fielddata.GetArray(i)
            ret[array_i.GetName()] = vtk_to_numpy(array_i)
        return ret
    def point_attributes(self):
        pointdata = self.ugrid_.GetPointData()
        ret = {}
        for i in range(pointdata.GetNumberOfArrays()):
            array_i = pointdata.GetArray(i)
            ret[array_i.GetName()] = vtk_to_numpy(array_i)
        return ret
    def cell_attributes(self):
        celldata = self.ugrid_.GetCellData()
        ret = {}
        for i in range(celldata.GetNumberOfArrays()):
            array_i = celldata.GetArray(i)
            ret[array_i.GetName()] = vtk_to_numpy(array_i)
        return ret
    def fielddata_array(self,name):
        fielddata = self.ugrid_.GetFieldData()
        array = fielddata.GetArray(name)
        if array is None:
            return None
        return vtk_to_numpy(array)
    def point_attribute_array(self,name):
        pointdata = self.ugrid_.GetPointData()
        array = pointdata.GetArray(name)
        if array is None:
            return None
        return vtk_to_numpy(array)
    def cell_attribute_array(self,name):
        celldata = self.ugrid_.GetCellData()
        array = celldata.GetArray(name)
        if array is None:
            return None
        return vtk_to_numpy(array)
    def get_bounding_box(self):
        return self.ugrid_.GetBounds()
    def get_bounding_box_size(self):
        x_min,x_max,y_min,y_max,z_min,z_max = self.ugrid_.GetBounds()
        return x_max-x_min,y_max-y_min,z_max-z_min
    def calc_cell_volumes(self):
        filter = vtk.vtkCellSizeFilter()
        filter.SetInputData(self.ugrid_)
        filter.Update()
        return vtk_to_numpy(filter.GetOutput().GetCellData().GetArray("Volume"))
    def extract_surface(self):
        # Issue: vtkGeometryFilter does not preserve face shape for quadratic elements
        geometryFilter = vtk.vtkGeometryFilter()
        geometryFilter.SetInputData(self.ugrid_)
        geometryFilter.Update()
        appendFilter = vtk.vtkAppendFilter()
        appendFilter.AddInputData(geometryFilter.GetOutput())
        appendFilter.Update()
        ret = VtuData()
        ret.ugrid_ = appendFilter.GetOutput()
        return ret


ATTRIBUTE_NAME_DISPLACEMENT = "DISPLACEMENT"
ATTRIBUTE_NAME_MISES_STRESS = "NodalMISES"


def clear_existing_objects():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def new_geometry_nodes(context, obj, geonodes_name):
    from bpy.app.translations import pgettext_data as gettext
    modifier = obj.modifiers.new(name=gettext("Geometry Nodes"), type='NODES')
    geonodes = bpy.data.node_groups.new(name=geonodes_name, type='GeometryNodeTree')
    geonodes.interface.new_socket(gettext("Geometry"), in_out='INPUT', socket_type='NodeSocketGeometry')
    geonodes.interface.new_socket(gettext("Geometry"), in_out='OUTPUT', socket_type='NodeSocketGeometry')
    input_node = geonodes.nodes.new('NodeGroupInput')
    input_node.select = False
    input_node.location.x = -200 - input_node.width
    output_node = geonodes.nodes.new('NodeGroupOutput')
    output_node.is_active_output = True
    output_node.select = False
    output_node.location.x = 200
    geonodes.links.new(input_node.outputs[0], output_node.inputs[0])
    geonodes.is_modifier = True
    modifier.node_group = geonodes
    return geonodes

def new_material_nodes(context, obj, material_name):
    material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    obj.data.materials.append(material)
    return material,material.node_tree

def fistr_import_vtu(self, context):
    import time as timer
    new_objects = []
    for file in self.files:
        t0 = timer.perf_counter()
        filepath = os.path.join(self.directory, file.name)
        objname = bpy.path.display_name_from_filepath(filepath)
        objname = objname.replace(".","_")
        print(f"objname = {objname}")
        
        # load vtu file and extract surface
        vtu = VtuData(filepath)
        vtu_surface = vtu.extract_surface()
        npoints = vtu_surface.npoints()
        ncells = vtu_surface.ncells()
        cellsize = numpy.cbrt(vtu.calc_cell_volumes().mean())
        connectivity = vtu_surface.cells_connectivity()
        offsets = vtu_surface.cells_offsets()
        attr_displacement = vtu_surface.point_attribute_array(ATTRIBUTE_NAME_DISPLACEMENT)
        attr_mises_stress = vtu_surface.point_attribute_array(ATTRIBUTE_NAME_MISES_STRESS)
        
        # Create mesh
        mesh_verts = vtu_surface.points()
        mesh_faces = [tuple(connectivity[offsets[i]:offsets[i+1]]) for i in range(ncells)]
        mesh = bpy.data.meshes.new(name=f"{objname}.mesh")
        mesh.from_pydata(mesh_verts,[],mesh_faces)
        mesh.update()
        
        # Create object
        obj = bpy_extras.object_utils.object_data_add(context, mesh, name=f"{objname}")
        new_objects.append(obj)
        
        # Set object properties
        obj.location = (0,0,0)
        obj.scale = (1,1,1)
        
        # Set object attributes
        mises_stress_min = 0.0
        mises_stress_max = 0.0
        if attr_displacement is not None:
            obj.data.attributes.new(name=ATTRIBUTE_NAME_DISPLACEMENT,type='FLOAT_VECTOR',domain='POINT')
            obj.data.attributes[ATTRIBUTE_NAME_DISPLACEMENT].data.foreach_set("vector", attr_displacement.flatten())
        if attr_mises_stress is not None:
            obj.data.attributes.new(name=ATTRIBUTE_NAME_MISES_STRESS,type='FLOAT',domain='POINT')
            obj.data.attributes[ATTRIBUTE_NAME_MISES_STRESS].data.foreach_set("value", attr_mises_stress)
            mises_stress_min = min(mises_stress_min,attr_mises_stress.min())
            mises_stress_max = max(mises_stress_max,attr_mises_stress.max())
        
        # Create material for surface
        material1,matnodes1 = new_material_nodes(context, obj, f"{objname}.material")
        
        node_p_BSDF = matnodes1.nodes["Principled BSDF"]
        node_output = matnodes1.nodes["Material Output"]
        
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
        
        node_p_BSDF = matnodes2.nodes["Principled BSDF"]
        node_output = matnodes2.nodes["Material Output"]
        
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
        
        node_input = geonodes.nodes["Group Input"]
        
        node_scenetime = geonodes.nodes.new(type="GeometryNodeInputSceneTime")
        node_scenetime.location.x = node_input.location.x-900
        node_scenetime.location.y = node_input.location.y-100
        
        node_clamp = geonodes.nodes.new(type="ShaderNodeClamp")
        node_clamp.inputs[1].default_value = 1
        node_clamp.inputs[2].default_value = 1
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
        # geonodes.links.new(node_valuetostring.outputs[0], node_joinstrings1.inputs[1])
        
        node_joinstrings2 = geonodes.nodes.new(type="GeometryNodeStringJoin")
        node_joinstrings2.inputs[0].default_value = "/"
        node_joinstrings2.location.x = node_inputstring2.location.x+node_inputstring2.width+40
        node_joinstrings2.location.y = node_inputstring2.location.y+50
        geonodes.links.new(node_inputstring2.outputs[0], node_joinstrings2.inputs[1])
        # geonodes.links.new(node_valuetostring.outputs[0], node_joinstrings2.inputs[1])
        
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
        geonodes.links.new(node_input.outputs["Geometry"], node_setposition.inputs["Geometry"])
        geonodes.links.new(node_scale.outputs[0], node_setposition.inputs["Offset"])
        
        node_maprange2 = geonodes.nodes.new(type="ShaderNodeMapRange")
        node_maprange2.inputs[1].default_value = mises_stress_min # From Min
        node_maprange2.inputs[2].default_value = mises_stress_max # From Max
        node_maprange2.inputs[3].default_value = 0.0 # To Min
        node_maprange2.inputs[4].default_value = 1.0 # To Max
        node_maprange2.location.x = node_inputattr2.location.x+node_inputattr2.width+40
        node_maprange2.location.y = node_inputattr2.location.y
        geonodes.links.new(node_inputattr2.outputs["Attribute"], node_maprange2.inputs["Value"])
        
        node_storeattr2 = geonodes.nodes.new(type="GeometryNodeStoreNamedAttribute")
        node_storeattr2.data_type = "FLOAT"
        node_storeattr2.domain = "POINT"
        node_storeattr2.inputs[2].default_value = "color_factor"
        node_storeattr2.location.x = node_setposition.location.x+node_setposition.width+40
        node_storeattr2.location.y = node_setposition.location.y
        node_storeattr2.width = 260
        geonodes.links.new(node_maprange2.outputs["Result"], node_storeattr2.inputs["Value"])
        geonodes.links.new(node_setposition.outputs["Geometry"], node_storeattr2.inputs["Geometry"])
        
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
        
        node_output = geonodes.nodes["Group Output"]
        node_output.location.x = node_joingeometry.location.x+node_joingeometry.width+40
        node_output.location.y = node_joingeometry.location.y
        geonodes.links.new(node_joingeometry.outputs[0], node_output.inputs["Geometry"])
        
        # finish
        t1 = timer.perf_counter()
        print(f"Successfully imported {filepath!r} in {t1-t0:.3f} sec")
    
    # Select created objects
    for obj in new_objects:
        obj.select_set(True)
    
    return {'FINISHED'}


class FISTR_ImportVtu(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "fistr.import_vtu"
    bl_label = "Import VTU files"
    bl_options = {'REGISTER','UNDO'}

    filter_glob: bpy.props.StringProperty(default="*.vtu;*.pvtu", options={'HIDDEN'})
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN','SKIP_SAVE'})

    def execute(self, context):
        return fistr_import_vtu(self, context)


def menu_func_import(self, context):
    self.layout.operator(FISTR_ImportVtu.bl_idname, text="FrontISTR VTU (.vtu|.pvtu)")

def register():
	bpy.utils.register_class(FISTR_ImportVtu)
	bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(FISTR_ImportVtu)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
