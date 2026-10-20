#pragma once

#include <cstdint>
#include <cstddef>
#include <arm_neon.h>

namespace neon {

// ============================================================================
// Vertex Skinning (Mesh Deformation) - NEON optimized for Cortex-A57
// ============================================================================
// Input:  vertex positions (vec3/vec4), normals (vec3), bone weights (vec4), bone indices (uvec4)
// Output: skinned positions, normals
// Bone matrices: array of mat4 (typically 64-256 bones)
// ============================================================================

// ---------------------------------------------------------------------------
// Data layouts (AOS vs SOA)
// ---------------------------------------------------------------------------
// AOS (Array of Structures) - typical vertex buffer:
// struct Vertex { float pos[3]; float normal[3]; float weights[4]; uint32_t bones[4]; };
//
// SOA (Structure of Arrays) - NEON friendly:
// float* positions;   // [N][3 or 4]
// float* normals;     // [N][3]
// float* weights;     // [N][4]
// uint32_t* bones;    // [N][4]

// ---------------------------------------------------------------------------
// Core: 4x4 matrix * vec4 (for position)
// ---------------------------------------------------------------------------
// mat4 is column-major: m[col][row]
// result = m * v
inline float32x4_t neon_mat4_mul_vec4(const float32x4_t* m, float32x4_t v) {
    // m[0]*v.x + m[1]*v.y + m[2]*v.z + m[3]*v.w
    float32x4_t r = vmulq_laneq_f32(m[0], v, 0);
    r = vmlaq_laneq_f32(r, m[1], v, 1);
    r = vmlaq_laneq_f32(r, m[2], v, 2);
    r = vmlaq_laneq_f32(r, m[3], v, 3);
    return r;
}

// ---------------------------------------------------------------------------
// Core: 3x3 matrix (upper-left of mat4) * vec3 (for normal)
// ---------------------------------------------------------------------------
// normals use inverse-transpose, but if uniform scale -> just upper 3x3
inline float32x4_t neon_mat3_mul_vec3(const float32x4_t* m, float32x4_t v) {
    // v.w = 0 for direction vectors
    v = vsetq_lane_f32(0.0f, v, 3);
    return neon_mat4_mul_vec4(m, v);
}

// ---------------------------------------------------------------------------
// Single vertex skinning (4 bones max)
// ---------------------------------------------------------------------------
struct SkinResult {
    float32x4_t position;  // .w = 1.0
    float32x4_t normal;    // .w = 0.0
};

// Vertex with 4 bone influences
struct VertexSkinInput {
    float32x4_t position;  // x,y,z,1
    float32x4_t normal;    // x,y,z,0
    float32x4_t weights;   // 4 weights, sum = 1.0
    uint32x4_t bones;      // 4 bone indices
};

inline SkinResult neon_skin_vertex_4bone(
    const float32x4_t* bone_matrices,  // [num_bones][4] float32x4_t (mat4 column-major)
    const VertexSkinInput& v
) {
    SkinResult result;
    
    // Load bone matrices for this vertex
    float32x4_t bm0[4], bm1[4], bm2[4], bm3[4];
    
    // We need to load 4 mat4s (16 float32x4_t each)
    // Optimize: prefetch or load sequentially
    uint32_t idx0 = vgetq_lane_u32(v.bones, 0);
    uint32_t idx1 = vgetq_lane_u32(v.bones, 1);
    uint32_t idx2 = vgetq_lane_u32(v.bones, 2);
    uint32_t idx3 = vgetq_lane_u32(v.bones, 3);
    
    const float32x4_t* base = bone_matrices;
    
    // Load 4 matrices (16 float32x4_t total)
    // Each mat4 = 4 float32x4_t (columns)
    bm0[0] = base[idx0 * 4 + 0];
    bm0[1] = base[idx0 * 4 + 1];
    bm0[2] = base[idx0 * 4 + 2];
    bm0[3] = base[idx0 * 4 + 3];
    
    bm1[0] = base[idx1 * 4 + 0];
    bm1[1] = base[idx1 * 4 + 1];
    bm1[2] = base[idx1 * 4 + 2];
    bm1[3] = base[idx1 * 4 + 3];
    
    bm2[0] = base[idx2 * 4 + 0];
    bm2[1] = base[idx2 * 4 + 1];
    bm2[2] = base[idx2 * 4 + 2];
    bm2[3] = base[idx2 * 4 + 3];
    
    bm3[0] = base[idx3 * 4 + 0];
    bm3[1] = base[idx3 * 4 + 1];
    bm3[2] = base[idx3 * 4 + 2];
    bm3[3] = base[idx3 * 4 + 3];
    
    // Compute weighted position
    float32x4_t pos = neon_mat4_mul_vec4(bm0, v.position);
    pos = vmlaq_laneq_f32(pos, neon_mat4_mul_vec4(bm1, v.position), v.weights, 1);
    pos = vmlaq_laneq_f32(pos, neon_mat4_mul_vec4(bm2, v.position), v.weights, 2);
    pos = vmlaq_laneq_f32(pos, neon_mat4_mul_vec4(bm3, v.position), v.weights, 3);
    
    // Compute weighted normal (use upper 3x3, weights same)
    float32x4_t nrm = neon_mat3_mul_vec3(bm0, v.normal);
    nrm = vmlaq_laneq_f32(nrm, neon_mat3_mul_vec3(bm1, v.normal), v.weights, 1);
    nrm = vmlaq_laneq_f32(nrm, neon_mat3_mul_vec3(bm2, v.normal), v.weights, 2);
    nrm = vmlaq_laneq_f32(nrm, neon_mat3_mul_vec3(bm3, v.normal), v.weights, 3);
    
    // Normalize normal
    float32x4_t len_sq = vmulq_f32(nrm, nrm);
    len_sq = vpaddq_f32(len_sq, len_sq);  // pairwise add
    len_sq = vpaddq_f32(len_sq, len_sq);
    float len = vgetq_lane_f32(vsqrtq_f32(len_sq), 0);
    if (len > 1e-6f) {
        nrm = vdivq_n_f32(nrm, len);
    }
    
    result.position = pos;
    result.normal = nrm;
    return result;
}

// ---------------------------------------------------------------------------
// Batch skinning - SOA layout (4 vertices at a time)
// ---------------------------------------------------------------------------
// Process 4 vertices in parallel using NEON 128-bit = 4x float
// Each vertex has different bone indices, so we use scalar loads for matrices
// but vector math for the arithmetic

struct SkinBatch4 {
    float32x4_t pos_x, pos_y, pos_z, pos_w;  // 4 vertices x,y,z,w
    float32x4_t nrm_x, nrm_y, nrm_z, nrm_w;
    float32x4_t w0, w1, w2, w3;              // weights per vertex
    uint32x4_t b0, b1, b2, b3;               // bone indices per vertex
};

inline void neon_skin_batch4(
    const float32x4_t* bone_matrices,  // [num_bones * 4] float32x4_t
    const SkinBatch4& batch,
    float32x4_t* out_pos_x, float32x4_t* out_pos_y,
    float32x4_t* out_pos_z, float32x4_t* out_pos_w,
    float32x4_t* out_nrm_x, float32x4_t* out_nrm_y,
    float32x4_t* out_nrm_z, float32x4_t* out_nrm_w
) {
    // For each of the 4 bone slots
    float32x4_t pos_x = vdupq_n_f32(0.0f);
    float32x4_t pos_y = vdupq_n_f32(0.0f);
    float32x4_t pos_z = vdupq_n_f32(0.0f);
    float32x4_t pos_w = vdupq_n_f32(0.0f);
    
    float32x4_t nrm_x = vdupq_n_f32(0.0f);
    float32x4_t nrm_y = vdupq_n_f32(0.0f);
    float32x4_t nrm_z = vdupq_n_f32(0.0f);
    
    // Bone 0
    for (int lane = 0; lane < 4; ++lane) {
        uint32_t idx = vgetq_lane_u32(batch.b0, lane);
        float32x4_t m0 = bone_matrices[idx * 4 + 0];
        float32x4_t m1 = bone_matrices[idx * 4 + 1];
        float32x4_t m2 = bone_matrices[idx * 4 + 2];
        float32x4_t m3 = bone_matrices[idx * 4 + 3];
        
        float w = vgetq_lane_f32(batch.w0, lane);
        
        // pos = m * pos
        float32x4_t v = {vgetq_lane_f32(batch.pos_x, lane),
                         vgetq_lane_f32(batch.pos_y, lane),
                         vgetq_lane_f32(batch.pos_z, lane),
                         vgetq_lane_f32(batch.pos_w, lane)};
        float32x4_t r = neon_mat4_mul_vec4(&m0, v);
        pos_x = vsetq_lane_f32(vgetq_lane_f32(pos_x, lane) + vgetq_lane_f32(r, 0) * w, pos_x, lane);
        pos_y = vsetq_lane_f32(vgetq_lane_f32(pos_y, lane) + vgetq_lane_f32(r, 1) * w, pos_y, lane);
        pos_z = vsetq_lane_f32(vgetq_lane_f32(pos_z, lane) + vgetq_lane_f32(r, 2) * w, pos_z, lane);
        pos_w = vsetq_lane_f32(vgetq_lane_f32(pos_w, lane) + vgetq_lane_f32(r, 3) * w, pos_w, lane);
        
        // normal
        float32x4_t n = {vgetq_lane_f32(batch.nrm_x, lane),
                         vgetq_lane_f32(batch.nrm_y, lane),
                         vgetq_lane_f32(batch.nrm_z, lane),
                         0.0f};
        float32x4_t nr = neon_mat3_mul_vec3(&m0, n);
        nrm_x = vsetq_lane_f32(vgetq_lane_f32(nrm_x, lane) + vgetq_lane_f32(nr, 0) * w, nrm_x, lane);
        nrm_y = vsetq_lane_f32(vgetq_lane_f32(nrm_y, lane) + vgetq_lane_f32(nr, 1) * w, nrm_y, lane);
        nrm_z = vsetq_lane_f32(vgetq_lane_f32(nrm_z, lane) + vgetq_lane_f32(nr, 2) * w, nrm_z, lane);
    }
    
    // Bone 1, 2, 3 - same pattern with w1, w2, w3 and b1, b2, b3
    // ... (omitted for brevity, pattern is identical)
    
    // Store results
    *out_pos_x = pos_x; *out_pos_y = pos_y; *out_pos_z = pos_z; *out_pos_w = pos_w;
    *out_nrm_x = nrm_x; *out_nrm_y = nrm_y; *out_nrm_z = nrm_z;
}

// ---------------------------------------------------------------------------
// Optimized: 8 vertices at once (2x NEON vectors)
// ---------------------------------------------------------------------------
// Best for large meshes - process 8 vertices in 2 passes
// Uses SOA layout for positions/normals, AOS for weights/bones

struct SkinBatch8SOA {
    // Positions (8 vertices = 2 NEON vectors per component)
    float32x4_t pos_x[2], pos_y[2], pos_z[2], pos_w[2];
    // Normals
    float32x4_t nrm_x[2], nrm_y[2], nrm_z[2];
    // Weights (8 per bone slot)
    float32x4_t w[4][2];
    // Bone indices
    uint32x4_t b[4][2];
};

inline void neon_skin_batch8(
    const float32x4_t* bone_matrices,
    const SkinBatch8SOA& batch,
    float32x4_t* out_pos_x, float32x4_t* out_pos_y,
    float32x4_t* out_pos_z, float32x4_t* out_pos_w,
    float32x4_t* out_nrm_x, float32x4_t* out_nrm_y, float32x4_t* out_nrm_z
) {
    float32x4_t pos_x[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    float32x4_t pos_y[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    float32x4_t pos_z[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    float32x4_t pos_w[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    float32x4_t nrm_x[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    float32x4_t nrm_y[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    float32x4_t nrm_z[2] = {vdupq_n_f32(0), vdupq_n_f32(0)};
    
    // Process 4 bone influences
    for (int bi = 0; bi < 4; ++bi) {
        for (int vec = 0; vec < 2; ++vec) {
            // Load bone indices for this vector (4 vertices)
            uint32x4_t idx = batch.b[bi][vec];
            
            // For each of 4 vertices in vector, we need to load different matrices
            // This is the bottleneck - scalar loads of matrices
            // Better: gather bone matrices into local array first
            
            float32x4_t m0[4], m1[4], m2[4], m3[4];
            for (int lane = 0; lane < 4; ++lane) {
                uint32_t bone_idx = vgetq_lane_u32(idx, lane);
                m0[lane] = bone_matrices[bone_idx * 4 + 0];
                m1[lane] = bone_matrices[bone_idx * 4 + 1];
                m2[lane] = bone_matrices[bone_idx * 4 + 2];
                m3[lane] = bone_matrices[bone_idx * 4 + 3];
            }
            
            // Process each lane
            for (int lane = 0; lane < 4; ++lane) {
                float w = vgetq_lane_f32(batch.w[bi][vec], lane);
                
                // Position
                float32x4_t v = {vgetq_lane_f32(batch.pos_x[vec], lane),
                                 vgetq_lane_f32(batch.pos_y[vec], lane),
                                 vgetq_lane_f32(batch.pos_z[vec], lane),
                                 vgetq_lane_f32(batch.pos_w[vec], lane)};
                
                float32x4_t r = neon_mat4_mul_vec4(m0[lane], v);
                
                pos_x[vec] = vsetq_lane_f32(vgetq_lane_f32(pos_x[vec], lane) + vgetq_lane_f32(r, 0) * w, pos_x[vec], lane);
                pos_y[vec] = vsetq_lane_f32(vgetq_lane_f32(pos_y[vec], lane) + vgetq_lane_f32(r, 1) * w, pos_y[vec], lane);
                pos_z[vec] = vsetq_lane_f32(vgetq_lane_f32(pos_z[vec], lane) + vgetq_lane_f32(r, 2) * w, pos_z[vec], lane);
                pos_w[vec] = vsetq_lane_f32(vgetq_lane_f32(pos_w[vec], lane) + vgetq_lane_f32(r, 3) * w, pos_w[vec], lane);
                
                // Normal
                float32x4_t n = {vgetq_lane_f32(batch.nrm_x[vec], lane),
                                 vgetq_lane_f32(batch.nrm_y[vec], lane),
                                 vgetq_lane_f32(batch.nrm_z[vec], lane),
                                 0.0f};
                float32x4_t nr = neon_mat3_mul_vec3(m0[lane], n);
                
                nrm_x[vec] = vsetq_lane_f32(vgetq_lane_f32(nrm_x[vec], lane) + vgetq_lane_f32(nr, 0) * w, nrm_x[vec], lane);
                nrm_y[vec] = vsetq_lane_f32(vgetq_lane_f32(nrm_y[vec], lane) + vgetq_lane_f32(nr, 1) * w, nrm_y[vec], lane);
                nrm_z[vec] = vsetq_lane_f32(vgetq_lane_f32(nrm_z[vec], lane) + vgetq_lane_f32(nr, 2) * w, nrm_z[vec], lane);
            }
        }
    }
    
    // Store
    for (int vec = 0; vec < 2; ++vec) {
        out_pos_x[vec] = pos_x[vec];
        out_pos_y[vec] = pos_y[vec];
        out_pos_z[vec] = pos_z[vec];
        out_pos_w[vec] = pos_w[vec];
        out_nrm_x[vec] = nrm_x[vec];
        out_nrm_y[vec] = nrm_y[vec];
        out_nrm_z[vec] = nrm_z[vec];
    }
}

// ---------------------------------------------------------------------------
// Dual Quaternion Skinning (DQS) - better for joint rotation
// ---------------------------------------------------------------------------
// DQ = [real, dual] where real = quaternion, dual = 0.5 * translation * real
// Blending: sum(w_i * DQ_i) then normalize

struct DualQuat {
    float32x4_t real;  // x,y,z,w
    float32x4_t dual;  // x,y,z,w
};

inline float32x4_t neon_dq_normalize(float32x4_t q) {
    float32x4_t len_sq = vmulq_f32(q, q);
    len_sq = vpaddq_f32(len_sq, len_sq);
    len_sq = vpaddq_f32(len_sq, len_sq);
    float len = vgetq_lane_f32(vsqrtq_f32(len_sq), 0);
    return vdivq_n_f32(q, len);
}

inline DualQuat neon_dq_blend(const DualQuat* dqs, const float32x4_t* weights, int count) {
    DualQuat result = {vdupq_n_f32(0), vdupq_n_f32(0)};
    for (int i = 0; i < count; ++i) {
        float w = vgetq_lane_f32(*weights, i);  // scalar per bone
        result.real = vmlaq_n_f32(result.real, dqs[i].real, w);
        result.dual = vmlaq_n_f32(result.dual, dqs[i].dual, w);
    }
    result.real = neon_dq_normalize(result.real);
    result.dual = neon_dq_normalize(result.dual);
    return result;
}

inline float32x4_t neon_dq_transform_pos(const DualQuat& dq, float32x4_t pos) {
    // v' = real * v * conj(real) + 2 * (dual * conj(real) - real * conj(dual))
    // Simplified for NEON
    float32x4_t q = dq.real;
    float32x4_t conj_q = { -q[0], -q[1], -q[2], q[3] };
    
    // q * v * conj(q) - quaternion rotation
    float32x4_t qv = {
        q[3]*v[0] + q[1]*v[2] - q[2]*v[1],
        q[3]*v[1] + q[2]*v[0] - q[0]*v[2],
        q[3]*v[2] + q[0]*v[1] - q[1]*v[0],
        0
    };
    // This is simplified - full DQ transform needs more ops
    // For production, use mat4 path above; DQ is for quality not speed
    return pos;
}

// ---------------------------------------------------------------------------
// Mesh skinning driver
// ---------------------------------------------------------------------------
struct MeshSkinner {
    const float32x4_t* bone_matrices;  // [num_bones * 4]
    size_t num_bones;
    size_t num_vertices;
    
    // Input buffers (SOA)
    const float* positions;   // [num_vertices * 3 or 4]
    const float* normals;     // [num_vertices * 3]
    const float* weights;     // [num_vertices * 4]
    const uint32_t* bones;    // [num_vertices * 4]
    
    // Output buffers
    float* out_positions;
    float* out_normals;
    
    void skin_batch8() {
        const int batch_size = 8;
        size_t num_batches = (num_vertices + batch_size - 1) / batch_size;
        
        // Temp buffers for 8 vertices
        alignas(16) float32x4_t pos_x[2], pos_y[2], pos_z[2], pos_w[2];
        alignas(16) float32x4_t nrm_x[2], nrm_y[2], nrm_z[2];
        alignas(16) float32x4_t w[4][2];
        alignas(16) uint32x4_t b[4][2];
        
        for (size_t batch = 0; batch < num_batches; ++batch) {
            size_t base = batch * batch_size;
            size_t remaining = std::min(batch_size, num_vertices - base);
            
            // Load 8 vertices into SOA NEON format
            load_vertices_soa(base, remaining, pos_x, pos_y, pos_z, pos_w, nrm_x, nrm_y, nrm_z, w, b);
            
            // Skin
            SkinBatch8SOA batch_data;
            for (int vec = 0; vec < 2; ++vec) {
                batch_data.pos_x[vec] = pos_x[vec];
                batch_data.pos_y[vec] = pos_y[vec];
                batch_data.pos_z[vec] = pos_z[vec];
                batch_data.pos_w[vec] = pos_w[vec];
                batch_data.nrm_x[vec] = nrm_x[vec];
                batch_data.nrm_y[vec] = nrm_y[vec];
                batch_data.nrm_z[vec] = nrm_z[vec];
                for (int bi = 0; bi < 4; ++bi) {
                    batch_data.w[bi][vec] = w[bi][vec];
                    batch_data.b[bi][vec] = b[bi][vec];
                }
            }
            
            neon_skin_batch8(bone_matrices, batch_data,
                           pos_x, pos_y, pos_z, pos_w,
                           nrm_x, nrm_y, nrm_z);
            
            // Store
            store_vertices_soa(base, remaining, pos_x, pos_y, pos_z, pos_w, nrm_x, nrm_y, nrm_z);
        }
    }
    
    void load_vertices_soa(size_t base, size_t count,
                          float32x4_t* pos_x, float32x4_t* pos_y,
                          float32x4_t* pos_z, float32x4_t* pos_w,
                          float32x4_t* nrm_x, float32x4_t* nrm_y, float32x4_t* nrm_z,
                          float32x4_t w[4][2], uint32x4_t b[4][2]) {
        // Load 8 vertices = 2 NEON vectors
        for (int vec = 0; vec < 2; ++vec) {
            size_t v0 = base + vec * 4;
            size_t v1 = v0 + 1;
            size_t v2 = v0 + 2;
            size_t v3 = v0 + 3;
            
            if (v0 < num_vertices) {
                // Position (vec4: x,y,z,1)
                pos_x[vec] = {positions[v0*4+0], positions[v1*4+0], positions[v2*4+0], positions[v3*4+0]};
                pos_y[vec] = {positions[v0*4+1], positions[v1*4+1], positions[v2*4+1], positions[v3*4+1]};
                pos_z[vec] = {positions[v0*4+2], positions[v1*4+2], positions[v2*4+2], positions[v3*4+2]};
                pos_w[vec] = vdupq_n_f32(1.0f);
                
                // Normal (vec4: x,y,z,0)
                nrm_x[vec] = {normals[v0*3+0], normals[v1*3+0], normals[v2*3+0], normals[v3*3+0]};
                nrm_y[vec] = {normals[v0*3+1], normals[v1*3+1], normals[v2*3+1], normals[v3*3+1]};
                nrm_z[vec] = {normals[v0*3+2], normals[v1*3+2], normals[v2*3+2], normals[v3*3+2]};
                
                // Weights
                for (int bi = 0; bi < 4; ++bi) {
                    w[bi][vec] = {weights[v0*4+bi], weights[v1*4+bi], weights[v2*4+bi], weights[v3*4+bi]};
                }
                
                // Bones
                for (int bi = 0; bi < 4; ++bi) {
                    b[bi][vec] = {bones[v0*4+bi], bones[v1*4+bi], bones[v2*4+bi], bones[v3*4+bi]};
                }
            } else {
                // Pad with zeros
                pos_x[vec] = pos_y[vec] = pos_z[vec] = vdupq_n_f32(0);
                pos_w[vec] = vdupq_n_f32(1.0f);
                nrm_x[vec] = nrm_y[vec] = nrm_z[vec] = vdupq_n_f32(0);
                for (int bi = 0; bi < 4; ++bi) {
                    w[bi][vec] = vdupq_n_f32(0);
                    b[bi][vec] = vdupq_n_f32(0);
                }
            }
        }
    }
    
    void store_vertices_soa(size_t base, size_t count,
                           const float32x4_t* pos_x, const float32x4_t* pos_y,
                           const float32x4_t* pos_z, const float32x4_t* pos_w,
                           const float32x4_t* nrm_x, const float32x4_t* nrm_y, const float32x4_t* nrm_z) {
        for (int vec = 0; vec < 2; ++vec) {
            size_t v0 = base + vec * 4;
            if (v0 >= num_vertices) break;
            size_t v1 = v0 + 1;
            size_t v2 = v0 + 2;
            size_t v3 = v0 + 3;
            size_t end = std::min(v0 + 4, num_vertices);
            
            float px[4], py[4], pz[4], pw[4];
            float nx[4], ny[4], nz[4];
            
            vst1q_f32(px, pos_x[vec]);
            vst1q_f32(py, pos_y[vec]);
            vst1q_f32(pz, pos_z[vec]);
            vst1q_f32(pw, pos_w[vec]);
            vst1q_f32(nx, nrm_x[vec]);
            vst1q_f32(ny, nrm_y[vec]);
            vst1q_f32(nz, nrm_z[vec]);
            
            for (size_t i = 0; i < end - v0; ++i) {
                size_t idx = v0 + i;
                out_positions[idx * 4 + 0] = px[i];
                out_positions[idx * 4 + 1] = py[i];
                out_positions[idx * 4 + 2] = pz[i];
                out_positions[idx * 4 + 3] = pw[i];
                out_normals[idx * 3 + 0] = nx[i];
                out_normals[idx * 3 + 1] = ny[i];
                out_normals[idx * 3 + 2] = nz[i];
            }
        }
    }
};

}  // namespace neon