import bpy
import math




# ------------------------------------------------------------------
# IMPORTANT !! : blender has it's own path specifying format as bellow that uses "/" and "//" at the beggining of a relative path.
# ------------------------------------------------------------------

# specify to your font path
font_path = r"//Fonts/JustAnotherHand-Regular.ttf"

# load the font file
font = bpy.data.fonts.load(font_path)






text_content = "some text for a fuckin test yeah"

# Create font curve data
font_curve = bpy.data.curves.new(name=text_content, type='FONT')
font_curve.body = text_content
font_curve.font = font


# # You can also set bold/italic fonts if needed:
# font_curve.font_bold = font
# font_curve.font_italic = font
# font_curve.font_bold_italic = font


# Create object using the curve data
text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

# Link object to scene
bpy.context.collection.objects.link(text_obj)


# Set transforms (location, rotation, scale)
text_obj.location = (1.0, 2.0, 3.0)    # location
text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 45)))
text_obj.scale = (2.0, 2.0, 2.0)    # scale


# # Optional: set text size, alignment, etc.
# # These are font properties, not object transforms.
# font_curve.size = 1.5
# font_curve.align_x = 'CENTER'
# font_curve.align_y = 'CENTER'













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



