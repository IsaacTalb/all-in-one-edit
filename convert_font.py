from fontTools.ttLib import TTFont
font = TTFont(r'C:\Users\thaun\Downloads\MyanmarPhiksel_Fonts\MyanmarPhiksel_Fonts\MyanmarPhiksel\Regular.woff2')
font.save(r'C:\Users\thaun\Downloads\MyanmarPhiksel_Fonts\MyanmarPhiksel_Fonts\MyanmarPhiksel\MyanmarPhiksel.ttf')
print('Converted to TTF')
