#pragma once

// ============================================================================
// Async Texture Streaming - CPU NEON + GPU Compute + VkQueue submit chain
// ============================================================================
// Pipeline: CPU NEON decode/convert → Staging Buffer → GPU Compute (format/mip) → VkImage
// Uses: neon_texture_upload.h (CPU) + compute_texture_upload.comp (GPU)
// ============================================================================

#include <vulkan/vulkan.h>
#include <vector>
#include <thread>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <functional>
#include <future>

namespace neon {

// Forward declare
struct TextureUploadTask;
class AsyncTextureStreamer;

// ---------------------------------------------------------------------------
// Task description
// ---------------------------------------------------------------------------
struct TextureUploadTask {
    // Source
    const uint8_t* cpu_data = nullptr;      // Raw pixel data (owned by caller until submit)
    size_t cpu_data_size = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t mip_levels = 1;
    VkFormat src_format = VK_FORMAT_R8G8B8A8_UNORM;  // CPU data format
    bool srgb_to_linear = false;
    bool premultiply_alpha = false;
    bool generate_mips = true;
    
    // Destination
    VkImage dst_image = VK_NULL_HANDLE;
    VkImageLayout dst_initial_layout = VK_IMAGE_LAYOUT_UNDEFINED;
    VkImageLayout dst_final_layout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    
    // Synchronization
    VkSemaphore wait_semaphore = VK_NULL_HANDLE;
    VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
    VkSemaphore signal_semaphore = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    
    // Callback
    std::function<void(VkResult)> callback;
    
    // Internal
    uint64_t task_id = 0;
};

// ---------------------------------------------------------------------------
// Streamer configuration
// ---------------------------------------------------------------------------
struct StreamerConfig {
    VkDevice device = VK_NULL_HANDLE;
    VkPhysicalDevice physical_device = VK_NULL_HANDLE;
    VkQueue transfer_queue = VK_NULL_HANDLE;
    uint32_t transfer_queue_family = 0;
    VkQueue compute_queue = VK_NULL_HANDLE;
    uint32_t compute_queue_family = 0;
    VkCommandPool transfer_cmd_pool = VK_NULL_HANDLE;
    VkCommandPool compute_cmd_pool = VK_NULL_HANDLE;
    
    // Staging buffer pool
    size_t staging_buffer_size = 64 * 1024 * 1024;  // 64 MB default
    uint32_t max_staging_buffers = 4;
    
    // Shader modules
    VkShaderModule texture_compute_shader = VK_NULL_HANDLE;  // compute_texture_upload.comp
    
    // Descriptor set layout for compute
    VkDescriptorSetLayout compute_descriptor_layout = VK_NULL_HANDLE;
    VkPipelineLayout compute_pipeline_layout = VK_NULL_HANDLE;
    VkPipeline compute_pipeline = VK_NULL_HANDLE;
};

// ---------------------------------------------------------------------------
// Staging buffer pool
// ---------------------------------------------------------------------------
class StagingBufferPool {
public:
    struct Buffer {
        VkBuffer buffer = VK_NULL_HANDLE;
        VkDeviceMemory memory = VK_NULL_HANDLE;
        void* mapped = nullptr;
        size_t size = 0;
        bool in_use = false;
        uint64_t last_used_frame = 0;
    };
    
    StagingBufferPool() = default;
    ~StagingBufferPool() { cleanup(); }
    
    bool init(VkDevice device, VkPhysicalDevice physical_device, size_t buffer_size, uint32_t count);
    void cleanup();
    
    Buffer* acquire(VkDevice device, VkPhysicalDevice physical_device, size_t min_size);
    void release(Buffer* buffer, uint64_t current_frame);
    
private:
    VkDevice device_ = VK_NULL_HANDLE;
    VkPhysicalDevice physical_device_ = VK_NULL_HANDLE;
    size_t buffer_size_ = 0;
    std::vector<Buffer> buffers_;
    std::mutex mutex_;
};

// ---------------------------------------------------------------------------
// Async Texture Streamer
// ---------------------------------------------------------------------------
class AsyncTextureStreamer {
public:
    AsyncTextureStreamer() = default;
    ~AsyncTextureStreamer() { shutdown(); }
    
    bool init(const StreamerConfig& config);
    void shutdown();
    
    // Submit texture upload task (returns immediately)
    // Task is processed asynchronously
    bool submit(TextureUploadTask&& task);
    
    // Submit and wait (synchronous)
    VkResult submit_sync(TextureUploadTask&& task);
    
    // Poll for completed tasks (call once per frame)
    void poll_completed();
    
    // Wait for all pending tasks
    void wait_idle();
    
    // Stats
    struct Stats {
        uint64_t submitted = 0;
        uint64_t completed = 0;
        uint64_t failed = 0;
        size_t bytes_uploaded = 0;
        double avg_upload_ms = 0.0;
    };
    Stats get_stats() const { return stats_; }
    
    // Frame advance (for staging buffer recycling)
    void next_frame(uint64_t frame_id);
    
private:
    // Worker threads
    void cpu_worker();
    void gpu_worker();
    
    // Process single task
    VkResult process_task_cpu(TextureUploadTask& task, StagingBufferPool::Buffer* staging);
    VkResult process_task_gpu(TextureUploadTask& task, StagingBufferPool::Buffer* staging);
    
    // Vulkan helpers
    VkResult create_staging_buffer(StagingBufferPool::Buffer* buf, size_t size);
    VkResult upload_to_image(TextureUploadTask& task, StagingBufferPool::Buffer* staging);
    VkResult run_compute_mips(TextureUploadTask& task, StagingBufferPool::Buffer* staging);
    
    // Command buffer management
    VkCommandBuffer get_transfer_cmd();
    VkCommandBuffer get_compute_cmd();
    void return_transfer_cmd(VkCommandBuffer cmd);
    void return_compute_cmd(VkCommandBuffer cmd);
    
    // Data
    StreamerConfig config_;
    StagingBufferPool staging_pool_;
    
    std::thread cpu_thread_;
    std::thread gpu_thread_;
    std::atomic<bool> running_{false};
    
    std::queue<TextureUploadTask> cpu_queue_;
    std::queue<std::pair<TextureUploadTask, StagingBufferPool::Buffer*>> gpu_queue_;
    
    std::mutex cpu_mutex_;
    std::mutex gpu_mutex_;
    std::condition_variable cpu_cv_;
    std::condition_variable gpu_cv_;
    
    std::vector<VkCommandBuffer> transfer_cmds_;
    std::vector<VkCommandBuffer> compute_cmds_;
    std::mutex cmd_mutex_;
    
    Stats stats_;
    uint64_t current_frame_ = 0;
    uint64_t next_task_id_ = 1;
    
    // Completed tasks for callback
    struct CompletedTask {
        TextureUploadTask task;
        VkResult result;
    };
    std::queue<CompletedTask> completed_queue_;
    std::mutex completed_mutex_;
};

// ---------------------------------------------------------------------------
// High-level convenience functions
// ---------------------------------------------------------------------------

// Simple one-shot upload (synchronous)
VkResult upload_texture_simple(
    VkDevice device,
    VkPhysicalDevice physical_device,
    VkQueue queue,
    VkCommandPool cmd_pool,
    VkImage dst_image,
    VkFormat dst_format,
    uint32_t width, uint32_t height, uint32_t mip_levels,
    const uint8_t* data, size_t data_size,
    VkFormat src_format,
    bool srgb_to_linear,
    bool generate_mips
);

// Async uploader with default config
AsyncTextureStreamer create_default_streamer(
    VkDevice device,
    VkPhysicalDevice physical_device,
    VkQueue transfer_queue,
    uint32_t transfer_queue_family,
    VkQueue compute_queue,
    uint32_t compute_queue_family,
    VkCommandPool transfer_cmd_pool,
    VkCommandPool compute_cmd_pool
);

// ---------------------------------------------------------------------------
// Inline implementations
// ---------------------------------------------------------------------------

inline void AsyncTextureStreamer::next_frame(uint64_t frame_id) {
    current_frame_ = frame_id;
    // Release old staging buffers
    staging_pool_.release_old_buffers(frame_id);
}

inline AsyncTextureStreamer::Stats AsyncTextureStreamer::get_stats() const {
    return stats_;
}

// ---------------------------------------------------------------------------
// Vulkan pipeline creation helpers (for compute shaders)
// ---------------------------------------------------------------------------

struct ComputePipelineBundle {
    VkShaderModule shader = VK_NULL_HANDLE;
    VkDescriptorSetLayout desc_layout = VK_NULL_HANDLE;
    VkPipelineLayout pipeline_layout = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
};

ComputePipelineBundle create_compute_pipeline(
    VkDevice device,
    const uint32_t* spirv_code,
    size_t spirv_size,
    const VkDescriptorSetLayoutBinding* bindings,
    uint32_t binding_count,
    const VkPushConstantRange* push_ranges,
    uint32_t push_range_count
);

void destroy_compute_pipeline(VkDevice device, ComputePipelineBundle& bundle);

// ---------------------------------------------------------------------------
// Descriptor set for texture compute
// ============================================================================
// set = 0
// binding 0: src_image (rgba8, read_only)
// binding 1: dst_image (rgba8, write_only)
// binding 2: src_pixels (storage buffer, read_only)
// binding 3: dst_pixels (storage buffer, write_only)
// binding 4: src_mip (storage buffer, read_only)
// binding 5: dst_mip (storage buffer, write_only)
//
// Push constants: PushConstants struct from compute_texture_upload.comp
// ============================================================================

inline std::array<VkDescriptorSetLayoutBinding, 6> get_texture_compute_bindings() {
    return {{
        {0, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},  // src_image
        {1, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},  // dst_image
        {2, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}, // src_pixels
        {3, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}, // dst_pixels
        {4, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}, // src_mip
        {5, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}, // dst_mip
    }};
}

inline VkPushConstantRange get_texture_compute_push_range() {
    return {
        VK_SHADER_STAGE_COMPUTE_BIT,
        0,
        sizeof(TextureComputePushConstants)  // Defined in compute shader
    };
}

}  // namespace neon