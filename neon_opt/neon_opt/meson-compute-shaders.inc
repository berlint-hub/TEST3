# ============================================================================
# Compute Shader SPIR-V Compilation for nxvk
# ============================================================================
# Add to src/vulkan/runtime/meson.build after ASTC decoder section (around line 298)
# ============================================================================

# Compute shader source files
nvk_compute_shader_sources = {
  'ubo_upload'        : 'compute_ubo_upload.comp',
  'vertex_skinning'   : 'compute_vertex_skinning.comp',
  'texture_upload'    : 'compute_texture_upload.comp',
  'frustum_culling'   : 'compute_frustum_culling.comp',
}

# Compile GLSL compute shaders to SPIR-V using glslangValidator
nvk_compute_shader_spv = {}
nvk_compute_shader_h = {}
foreach name, src : nvk_compute_shader_sources
  if prog_glslang.found()
    # Compile to SPIR-V binary
    nvk_compute_shader_spv[name] = custom_target(
      'nvk_' + name + '_spv',
      input : src,
      output : name + '.spv',
      command : [
        prog_glslang, '-V', '-S', 'comp', '-x', '-o', '@OUTPUT@', '@INPUT@',
        glslang_quiet, glslang_depfile,
      ],
      depfile : name + '.spv.d',
      build_by_default : true,
    )
    
    # Generate C header with SPIR-V embedded as array
    nvk_compute_shader_h[name] = custom_target(
      'nvk_' + name + '_spv_h',
      input : nvk_compute_shader_spv[name],
      output : 'nvk_' + name + '_spv.h',
      command : [
        prog_python, '-c', '''
import sys
with open(sys.argv[1], "rb") as f:
    data = f.read()
with open(sys.argv[2], "w") as f:
    f.write("// Auto-generated from " + sys.argv[1] + "\\n")
    f.write("#pragma once\\n")
    f.write("#include <vulkan/vulkan.h>\\n\\n")
    f.write("static const uint32_t nvk_" + sys.argv[3] + "_spv[] = {\\n")
    for i in range(0, len(data), 4):
        word = int.from_bytes(data[i:i+4], "little")
        f.write("  0x{:08x},\\n".format(word))
    f.write("};\\n\\n")
    f.write("static const size_t nvk_" + sys.argv[3] + "_spv_size = " + str(len(data)) + ";\\n")
        ''',
        '@INPUT@', '@OUTPUT@', name,
      ],
      build_by_default : true,
    )
  else
    warning('glslangValidator not found, compute shaders will not be available')
    nvk_compute_shader_h[name] = []
  endif
endforeach

# Create a unified header for all compute shaders
nvk_compute_shaders_h = custom_target(
  'nvk_compute_shaders_h',
  input : [
    nvk_compute_shader_h['ubo_upload'],
    nvk_compute_shader_h['vertex_skinning'],
    nvk_compute_shader_h['texture_upload'],
    nvk_compute_shader_h['frustum_culling'],
  ],
  output : 'nvk_compute_shaders.h',
  command : [
    prog_python, '-c', '''
import sys
outputs = sys.argv[1:]
with open(sys.argv[1], "w") as out:
    out.write("// Auto-generated unified compute shader header\\n")
    out.write("#pragma once\\n")
    out.write("#include <vulkan/vulkan.h>\\n\\n")
    for f in outputs:
        with open(f, "r") as inf:
            out.write(inf.read())
            out.write("\\n")
    out.write("// Shader creation helper\\n")
    out.write("VkResult nvk_create_compute_shader_module(VkDevice device, const char* name, VkShaderModule* out_module);\\n")
''',
    '@OUTPUT@',
  ],
  build_by_default : true,
)

# C source file with shader module creation helper
nvk_compute_shaders_c = custom_target(
  'nvk_compute_shaders_c',
  input : nvk_compute_shaders_h,
  output : 'nvk_compute_shaders.c',
  command : [
    prog_python, '-c', '''
import sys
import re
with open(sys.argv[1], "r") as f:
    content = f.read()

# Extract shader names and sizes
shaders = []
for match in re.finditer(r'static const uint32_t nvk_(\w+)_spv\[\] = \{(.*?)\};', content, re.DOTALL):
    name = match.group(1)
    size_match = re.search(r'static const size_t nvk_\w+_spv_size = (\d+);', content)
    size = int(size_match.group(1)) if size_match else 0
    shaders.append((name, size))

with open(sys.argv[2], "w") as out:
    out.write("// Auto-generated compute shader module creation\\n")
    out.write("#include \"nvk_compute_shaders.h\"\\n")
    out.write("#include <vulkan/vulkan.h>\\n\\n")
    
    for name, size in shaders:
        out.write("extern const uint32_t nvk_{}_spv[];\\n".format(name))
        out.write("extern const size_t nvk_{}_spv_size;\\n\\n".format(name))
    
    out.write("VkResult nvk_create_compute_shader_module(VkDevice device, const char* name, VkShaderModule* out_module) {\\n")
    for name, size in shaders:
        out.write("  if (strcmp(name, \"{}\") == 0) {{\\n".format(name))
        out.write("    VkShaderModuleCreateInfo info = {{\\n")
        out.write("      .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,\\n")
        out.write("      .codeSize = nvk_{}_spv_size,\\n".format(name))
        out.write("      .pCode = nvk_{}_spv,\\n".format(name))
        out.write("    }};\\n")
        out.write("    return vkCreateShaderModule(device, &info, NULL, out_module);\\n")
        out.write("  }\\n")
    out.write("  return VK_ERROR_UNKNOWN;\\n")
    out.write("}\\n")
''',
    '@INPUT@', '@OUTPUT@',
  ],
  build_by_default : true,
)

# Add to vulkan_runtime_files if glslang is available
if prog_glslang.found()
  vulkan_runtime_files += [
    nvk_compute_shaders_c,
    nvk_compute_shaders_h,
  ]
  
  # Add headers to generated dependencies
  vulkan_runtime_header_gen_deps = declare_dependency(
    sources : vulkan_runtime_header_gen_deps.sources + [nvk_compute_shaders_h[0]],
  )
endif

# Declare dependency for other modules
idep_nvk_compute_shaders = declare_dependency(
  sources : prog_glslang.found() ? [nvk_compute_shaders_c] : [],
  include_directories : include_directories('.'),
  dependencies : prog_glslang.found() ? [idep_vulkan_runtime_headers] : [],
)

# Install headers for external use
install_headers('nvk_compute_shaders.h', subdir: 'vulkan')