import bpy
import math, copy

InputList = [ [10000, 60000], [80000, 50000], [102500, 20000], [175000, 30000] ] 
input_quantum_time: float = 3
input_cs_time: float = 1





original_input_list = copy.deepcopy(InputList)
scale = 0.0001

for p in original_input_list:
    p[0] *= scale
    p[1] *= scale










# (1) Scene preperations like loading the fonts, ...

# ------------------------------------------------------------------
# IMPORTANT !! : blender has it's own path specifying format as bellow that uses "/" and "//" at the beggining of a relative path.
# ------------------------------------------------------------------
# specifying the font path
font_path = r"//Fonts/JustAnotherHand-Regular.ttf"

# load the font file
font = bpy.data.fonts.load(font_path)











y_cordinate = -4

for p in original_input_list:    # creating the p_i text objects

    text_content = f"p{original_input_list.index(p)}"    # numbers the p's based on their index which is the same as pid

    # Create font curve data
    font_curve = bpy.data.curves.new(name=text_content, type='FONT')
    font_curve.body = text_content
    font_curve.font = font

    # Create object using the curve data
    text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

    # Link object to scene
    bpy.context.collection.objects.link(text_obj)

    # Set transforms (location, rotation, scale)
    text_obj.location = (1.4, y_cordinate, 0)    # location (in meters)
    text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    text_obj.scale = (0.5, 0.5, 0.5)    # scale

    # incrementing y
    y_cordinate += 0.5


for p in original_input_list:    # creating the at_i text objects

    text_content = f"{p[0]}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=text_content, type='FONT')
    font_curve.body = text_content
    font_curve.font = font

    # Create object using the curve data
    text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

    # Link object to scene
    bpy.context.collection.objects.link(text_obj)

    # Set transforms (location, rotation, scale)
    text_obj.location = (0, y_cordinate, 0)    # location (in meters)
    text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    text_obj.scale = (0.5, 0.5, 0.5)    # scale

    # incrementing y
    y_cordinate += 0.5












# # Complete example
# import bpy

# # Create text data
# font_curve = bpy.data.curves.new(name="MyText", type='FONT')
# font_curve.body = "Hello World"
# font_curve.size = 1.2
# font_curve.align_x = 'CENTER'

# # Load font
# font_path = r"C:\Windows\Fonts\arial.ttf"
# font = bpy.data.fonts.load(font_path)
# font_curve.font = font

# # Create object
# text_obj = bpy.data.objects.new(name="TextObject", object_data=font_curve)
# bpy.context.collection.objects.link(text_obj)

# # Set transforms
# text_obj.location = (0, 0, 1)
# text_obj.rotation_euler = (0, 0, 0.5)
# text_obj.scale = (1.5, 1.5, 1.5)






# ----------------------------------------------------------------------------------------


# # Clear the default scene
# bpy.ops.object.select_all(action='SELECT')
# bpy.ops.object.delete(use_global=False)

# # Remove all materials from the file
# for mat in list(bpy.data.materials):
#     bpy.data.materials.remove(mat)

# ----------------------------------------------------------------------------------------

# # Create materials
# arrival_mat = bpy.data.materials.new(name="ArrivalGreen")
# arrival_mat.diffuse_color = (0, 1, 0, 1)

# execution_mat = bpy.data.materials.new(name="ExecutionBlue")
# execution_mat.diffuse_color = (0, 0, 1, 1)

# cs_mat = bpy.data.materials.new(name="ContextSwitchRed")
# cs_mat.diffuse_color = (1, 0, 0, 1)

# label_mat = bpy.data.materials.new(name="LabelBlack")
# label_mat.diffuse_color = (0, 0, 0, 1)

# ----------------------------------------------------------------------------------------



