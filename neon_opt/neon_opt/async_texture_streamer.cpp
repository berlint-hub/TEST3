#include "async_texture_streamer.h"
#include <vulkan/vulkan.h>
#include <cstring>
#include <algorithm>

namespace neon {

// ---------------------------------------------------------------------------
// StagingBufferPool implementation
// ---------------------------------------------------------------------------

bool StagingBufferPool::init(VkDevice device, VkPhysicalDevice physical_device, size_t buffer_size, uint32_t count) {
    device_ = device;
    physical_device_ = physical_device;
    buffer_size_ = buffer_size;
    buffers_.resize(count);
    return true;
}

void StagingBufferPool::cleanup() {
    for (auto& buf : buffers_) {
        if (buf.buffer != VK_NULL_HANDLE) {
            // Note: device_ might be invalid if device was destroyed
            // In practice, caller should ensure device outlives pool
        }
        if (buf.memory != VK_NULL_HANDLE) {
            // vkFreeMemory(device_, buf.memory, nullptr);
        }
    }
    buffers_.clear();
}

StagingBufferPool::Buffer* StagingBufferPool::acquire(VkDevice device, VkPhysicalDevice physical_device, size_t min_size) {
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto& buf : buffers_) {
        if (!buf.in_use && buf.size >= min_size) {
            buf.in_use = true;
            return &buf;
        }
    }
    // Need to create new buffer - simplified implementation
    return nullptr;
}

void StagingBufferPool::release(Buffer* buffer, uint64_t current_frame) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (buffer) {
        buffer->in_use = false;
        buffer->last_used_frame = current_frame;
    }
}

// ---------------------------------------------------------------------------
// AsyncTextureStreamer implementation
// ---------------------------------------------------------------------------

bool AsyncTextureStreamer::init(const StreamerConfig& config) {
    if (running_.load()) return false;
    
    config_ = config;
    
    // Initialize staging buffer pool
    if (!staging_pool_.init(config_.device, config_.physical_device, config_.staging_buffer_size, config_.max_staging_buffers)) {
        return false;
    }
    
    // Load pipeline cache if path provided
    if (config_.pipeline_cache_path) {
        VkPipelineCacheCreateInfo cache_info = {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO,
            .pNext = nullptr,
            .flags = 0,
            .initialDataSize = 0,
            .pInitialData = nullptr
        };
        
        // Try to load existing cache data
        if (config_.pipeline_cache_path) {
            std::ifstream file(config_.pipeline_cache_path, std::ios::binary | std::ios::ate);
            if (file.is_open()) {
                size_t file_size = static_cast<size_t>(file.tellg());
                file.seekg(0, std::ios::beg);
                if (file_size > 0) {
                    std::vector<uint8_t> cache_data(file_size);
                    file.read(reinterpret_cast<char*>(cache_data.data()), file_size);
                    if (file) {
                        cache_info.initialDataSize = cache_data.size();
                        cache_info.pInitialData = cache_data.data();
                    }
                }
            }
        }
        
        VkResult result = vkCreatePipelineCache(config_.device, &cache_info, nullptr, &config_.pipeline_cache);
        if (result != VK_SUCCESS) {
            config_.pipeline_cache = VK_NULL_HANDLE;
        }
    }
    
    // Create command pools if not provided
    if (!config_.transfer_cmd_pool) {
        VkCommandPoolCreateInfo pool_info = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
            .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
            .queueFamilyIndex = config_.transfer_queue_family,
        };
        vkCreateCommandPool(config_.device, &pool_info, nullptr, &config_.transfer_cmd_pool);
    }
    
    if (!config_.compute_cmd_pool) {
        VkCommandPoolCreateInfo pool_info = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
            .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
            .queueFamilyIndex = config_.compute_queue_family,
        };
        vkCreateCommandPool(config_.device, &pool_info, nullptr, &config_.compute_cmd_pool);
    }
    
    // Create descriptor set layout for compute
    auto bindings = get_texture_compute_bindings();
    VkDescriptorSetLayoutCreateInfo layout_info = {
        .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
        .bindingCount = static_cast<uint32_t>(bindings.size()),
        .pBindings = bindings.data(),
    };
    vkCreateDescriptorSetLayout(config_.device, &layout_info, nullptr, &config_.compute_descriptor_layout);
    
    // Create pipeline layout
    VkPushConstantRange push_range = get_texture_compute_push_range();
    VkPipelineLayoutCreateInfo pl_info = {
        .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .setLayoutCount = 1,
        .pSetLayouts = &config_.compute_descriptor_layout,
        .pushConstantRangeCount = 1,
        .pPushConstantRanges = &push_range,
    };
    vkCreatePipelineLayout(config_.device, &pl_info, nullptr, &config_.compute_pipeline_layout);
    
    // Create compute pipeline if shader module provided
    if (config_.texture_compute_shader) {
        VkPipelineShaderStageCreateInfo stage = {
            .sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_COMPUTE_BIT,
            .module = config_.texture_compute_shader,
            .pName = "main",
        };
        VkComputePipelineCreateInfo cp_info = {
            .sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
            .stage = stage,
            .layout = config_.compute_pipeline_layout,
        };
        vkCreateComputePipelines(config_.device, config_.pipeline_cache, 1, &cp_info, nullptr, &config_.compute_pipeline);
    }
    
    // Load pipeline cache if exists
    load_pipeline_cache();
    
    // Start worker threads
    running_.store(true);
    cpu_thread_ = std::thread(&AsyncTextureStreamer::cpu_worker, this);
    gpu_thread_ = std::thread(&AsyncTextureStreamer::gpu_worker, this);
    
    return true;
}

void AsyncTextureStreamer::shutdown() {
    if (!running_.exchange(false)) return;
    
    // Save pipeline cache before shutdown
    save_pipeline_cache();
    
    // Wait for worker threads
    if (cpu_thread_.joinable()) cpu_thread_.join();
    if (gpu_thread_.joinable()) gpu_thread_.join();
    
    // Cleanup Vulkan resources
    if (config_.compute_pipeline) vkDestroyPipeline(config_.device, config_.compute_pipeline, nullptr);
    if (config_.compute_pipeline_layout) vkDestroyPipelineLayout(config_.device, config_.compute_pipeline_layout, nullptr);
    if (config_.compute_descriptor_layout) vkDestroyDescriptorSetLayout(config_.device, config_.compute_descriptor_layout, nullptr);
    if (config_.pipeline_cache) vkDestroyPipelineCache(config_.device, config_.pipeline_cache, nullptr);
    
    staging_pool_.cleanup();
    
    // Clear queues
    {
        std::lock_guard<std::mutex> lock(cpu_mutex_);
        while (!cpu_queue_.empty()) cpu_queue_.pop();
    }
    {
        std::lock_guard<std::mutex> lock(gpu_mutex_);
        while (!gpu_queue_.empty()) gpu_queue_.pop();
    }
    {
        std::lock_guard<std::mutex> lock(completed_mutex_);
        while (!completed_queue_.empty()) completed_queue_.pop();
    }
}

void AsyncTextureStreamer::cpu_worker() {
    while (running_.load()) {
        TextureUploadTask task;
        {
            std::unique_lock<std::mutex> lock(cpu_mutex_);
            cpu_cv_.wait(lock, [this] { return !cpu_queue_.empty() || !running_.load(); });
            if (!running_.load() && cpu_queue_.empty()) break;
            if (cpu_queue_.empty()) continue;
            task = std::move(cpu_queue_.front());
            cpu_queue_.pop();
        }
        
        // Acquire staging buffer
        size_t data_size = task.cpu_data_size;
        if (data_size == 0) data_size = task.width * task.height * 4;  // RGBA8
        
        StagingBufferPool::Buffer* staging = staging_pool_.acquire(config_.device, config_.physical_device, data_size);
        if (!staging) {
            // Handle error
            {
                std::lock_guard<std::mutex> lock(completed_mutex_);
                completed_queue_.push({std::move(task), VK_ERROR_OUT_OF_DEVICE_MEMORY});
            }
            continue;
        }
        
        VkResult result = process_task_cpu(task, staging);
        
        if (result == VK_SUCCESS) {
            std::lock_guard<std::mutex> lock(gpu_mutex_);
            gpu_queue_.push({std::move(task), staging});
            gpu_cv_.notify_one();
        } else {
            staging_pool_.release(staging, current_frame_);
            std::lock_guard<std::mutex> lock(completed_mutex_);
            completed_queue_.push({std::move(task), result});
        }
    }
}

void AsyncTextureStreamer::gpu_worker() {
    while (running_.load()) {
        std::pair<TextureUploadTask, StagingBufferPool::Buffer*> work;
        {
            std::unique_lock<std::mutex> lock(gpu_mutex_);
            gpu_cv_.wait(lock, [this] { return !gpu_queue_.empty() || !running_.load(); });
            if (!running_.load() && gpu_queue_.empty()) break;
            if (gpu_queue_.empty()) continue;
            work = std::move(gpu_queue_.front());
            gpu_queue_.pop();
        }
        
        VkResult result = process_task_gpu(work.first, work.second);
        
        staging_pool_.release(work.second, current_frame_);
        
        std::lock_guard<std::mutex> lock(completed_mutex_);
        completed_queue_.push({std::move(work.first), result});
    }
}

VkResult AsyncTextureStreamer::process_task_cpu(TextureUploadTask& task, StagingBufferPool::Buffer* staging) {
    // Map staging buffer
    if (!staging->mapped) {
        VkResult result = vkMapMemory(config_.device, staging->memory, 0, staging->size, 0, &staging->mapped);
        if (result != VK_SUCCESS) return result;
    }
    
    // Copy CPU data to staging buffer with NEON-optimized conversions
    if (task.cpu_data && task.cpu_data_size > 0) {
        size_t copy_size = std::min(task.cpu_data_size, staging->size);
        if (task.srgb_to_linear) {
            neon::neon_srgb_to_linear_staging(staging->mapped, task.cpu_data, copy_size);
        } else if (task.premultiply_alpha) {
            neon::neon_premultiply_alpha_staging(staging->mapped, task.cpu_data, task.cpu_data_size / 4);
        } else {
            neon::neon_copy_128(staging->mapped, task.cpu_data, copy_size);
        }
    }
    
    return VK_SUCCESS;
}

VkResult AsyncTextureStreamer::process_task_gpu(TextureUploadTask& task, StagingBufferPool::Buffer* staging) {
    VkCommandBuffer cmd = get_compute_cmd();
    
    // Begin command buffer
    VkCommandBufferBeginInfo begin_info = {
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
    };
    vkBeginCommandBuffer(cmd, &begin_info);
    
    // Run compute shader for mip generation if needed
    if (task.generate_mips && task.mip_levels > 1) {
        run_compute_mips(task, staging);
    }
    
    // Copy staging buffer to image
    VkBufferImageCopy region = {
        .bufferOffset = 0,
        .bufferRowLength = task.width,
        .bufferImageHeight = task.height,
        .imageSubresource = {
            .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
            .mipLevel = 0,
            .baseArrayLayer = 0,
            .layerCount = 1,
        },
        .imageOffset = {0, 0, 0},
        .imageExtent = {task.width, task.height, 1},
    };
    vkCmdCopyBufferToImage(cmd, staging->buffer, task.dst_image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
    
    // Generate mips via blit if needed
    if (task.generate_mips && task.mip_levels > 1) {
        // ... mip blit commands
    }
    
    // Transition to final layout
    VkImageMemoryBarrier barrier = {
        .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = VK_ACCESS_SHADER_READ_BIT,
        .oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
        .newLayout = task.dst_final_layout,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = task.dst_image,
        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, task.mip_levels, 0, 1},
    };
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
    
    vkEndCommandBuffer(cmd);
    
    // Submit
    VkSubmitInfo submit = {
        .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1,
        .pCommandBuffers = &cmd,
    };
    return vkQueueSubmit(config_.transfer_queue, 1, &submit, task.fence);
}

VkResult AsyncTextureStreamer::create_staging_buffer(StagingBufferPool::Buffer* buf, size_t size) {
    VkBufferCreateInfo bci = {
        .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = size,
        .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,
    };
    VkResult result = vkCreateBuffer(config_.device, &bci, nullptr, &buf->buffer);
    if (result != VK_SUCCESS) return result;
    
    VkMemoryRequirements mem_req;
    vkGetBufferMemoryRequirements(config_.device, buf->buffer, &mem_req);
    
    VkMemoryAllocateInfo ai = {
        .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = mem_req.size,
        .memoryTypeIndex = 0,  // Simplified - should find proper type
    };
    result = vkAllocateMemory(config_.device, &ai, nullptr, &buf->memory);
    if (result != VK_SUCCESS) return result;
    
    result = vkBindBufferMemory(config_.device, buf->buffer, buf->memory, 0);
    if (result != VK_SUCCESS) return result;
    
    buf->size = mem_req.size;
    return VK_SUCCESS;
}

VkResult AsyncTextureStreamer::upload_to_image(TextureUploadTask& task, StagingBufferPool::Buffer* staging) {
    // Handled in process_task_gpu
    return VK_SUCCESS;
}

VkResult AsyncTextureStreamer::run_compute_mips(TextureUploadTask& task, StagingBufferPool::Buffer* staging) {
    // Dispatch compute shader for mip generation
    // Simplified - actual implementation would dispatch compute_texture_upload.comp
    return VK_SUCCESS;
}

VkCommandBuffer AsyncTextureStreamer::get_transfer_cmd() {
    std::lock_guard<std::mutex> lock(cmd_mutex_);
    if (transfer_cmds_.empty()) {
        VkCommandBufferAllocateInfo ai = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
            .commandPool = config_.transfer_cmd_pool,
            .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
            .commandBufferCount = 1,
        };
        VkCommandBuffer cmd;
        vkAllocateCommandBuffers(config_.device, &ai, &cmd);
        transfer_cmds_.push_back(cmd);
    }
    VkCommandBuffer cmd = transfer_cmds_.back();
    transfer_cmds_.pop_back();
    return cmd;
}

VkCommandBuffer AsyncTextureStreamer::get_compute_cmd() {
    std::lock_guard<std::mutex> lock(cmd_mutex_);
    if (compute_cmds_.empty()) {
        VkCommandBufferAllocateInfo ai = {
            .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
            .commandPool = config_.compute_cmd_pool,
            .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
            .commandBufferCount = 1,
        };
        VkCommandBuffer cmd;
        vkAllocateCommandBuffers(config_.device, &ai, &cmd);
        compute_cmds_.push_back(cmd);
    }
    VkCommandBuffer cmd = compute_cmds_.back();
    compute_cmds_.pop_back();
    return cmd;
}

void AsyncTextureStreamer::return_transfer_cmd(VkCommandBuffer cmd) {
    std::lock_guard<std::mutex> lock(cmd_mutex_);
    transfer_cmds_.push_back(cmd);
}

void AsyncTextureStreamer::return_compute_cmd(VkCommandBuffer cmd) {
    std::lock_guard<std::mutex> lock(cmd_mutex_);
    compute_cmds_.push_back(cmd);
}

bool AsyncTextureStreamer::submit(TextureUploadTask&& task) {
    if (!running_.load()) return false;
    
    task.task_id = next_task_id_++;
    
    {
        std::lock_guard<std::mutex> lock(cpu_mutex_);
        cpu_queue_.push(std::move(task));
    }
    cpu_cv_.notify_one();
    return true;
}

VkResult AsyncTextureStreamer::submit_sync(TextureUploadTask&& task) {
    // Simplified synchronous version
    task.task_id = next_task_id_++;
    StagingBufferPool::Buffer* staging = staging_pool_.acquire(config_.device, config_.physical_device, task.width * task.height * 4);
    if (!staging) return VK_ERROR_OUT_OF_DEVICE_MEMORY;
    
    VkResult result = process_task_cpu(task, staging);
    if (result == VK_SUCCESS) {
        result = process_task_gpu(task, staging);
    }
    staging_pool_.release(staging, current_frame_);
    return result;
}

void AsyncTextureStreamer::poll_completed() {
    std::lock_guard<std::mutex> lock(completed_mutex_);
    while (!completed_queue_.empty()) {
        auto completed = std::move(completed_queue_.front());
        completed_queue_.pop();
        
        if (completed.task.callback) {
            completed.task.callback(completed.result);
        }
        
        if (completed.result == VK_SUCCESS) {
            stats_.completed++;
            stats_.bytes_uploaded += completed.task.cpu_data_size;
        } else {
            stats_.failed++;
        }
    }
}

void AsyncTextureStreamer::wait_idle() {
    // Wait for all queues to empty
    while (running_.load()) {
        {
            std::lock_guard<std::mutex> lock(cpu_mutex_);
            if (!cpu_queue_.empty()) break;
        }
        {
            std::lock_guard<std::mutex> lock(gpu_mutex_);
            if (!gpu_queue_.empty()) break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
}

// ---------------------------------------------------------------------------
// High-level convenience functions
// ---------------------------------------------------------------------------

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
) {
    // Simplified implementation
    return VK_SUCCESS;
}

AsyncTextureStreamer create_default_streamer(
    VkDevice device,
    VkPhysicalDevice physical_device,
    VkQueue transfer_queue,
    uint32_t transfer_queue_family,
    VkQueue compute_queue,
    uint32_t compute_queue_family,
    VkCommandPool transfer_cmd_pool,
    VkCommandPool compute_cmd_pool
) {
    AsyncTextureStreamer streamer;
    StreamerConfig config = {
        .device = device,
        .physical_device = physical_device,
        .transfer_queue = transfer_queue,
        .transfer_queue_family = transfer_queue_family,
        .compute_queue = compute_queue,
        .compute_queue_family = compute_queue_family,
        .transfer_cmd_pool = transfer_cmd_pool,
        .compute_cmd_pool = compute_cmd_pool,
        .pipeline_cache_path = "sdmc:/switch/.cache/nxvk_pipeline_cache.bin",
    };
    streamer.init(config);
    return streamer;
}

}  // namespace neon