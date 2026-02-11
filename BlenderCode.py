import bpy





# specify to your font path
font_path = r"C:\Windows\Fonts\arial.ttf"

# load the font file
font = bpy.data.fonts.load(font_path)




# Create font curve data
font_curve = bpy.data.curves.new(name="MyText", type='FONT')
font_curve.body = "WTF"
font_curve.font = font


# Create object using the curve data
text_obj = bpy.data.objects.new(name="TextObject", object_data=font_curve)

# Link object to scene
bpy.context.collection.objects.link(text_obj)

























