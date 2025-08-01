import json
import argparse
import numpy as np
from pathlib import Path
from omegaconf import OmegaConf
from vispy import app, scene
from vispy.scene import visuals
import open3d as o3d
from scipy.spatial.transform import Rotation as R
from dataclasses import dataclass, field


# --- Data Structures ---


@dataclass
class ScenePaths:
    """Manages all paths for a given scene."""

    scene_name: str
    base_dir: Path = Path("tmp")
    workdir: Path = field(init=False)
    points3d_txt: Path = field(init=False)
    images_txt: Path = field(init=False)
    image_dir: Path = field(init=False)
    camera_txt: Path = field(init=False)

    def __post_init__(self):
        self.workdir = self.base_dir / self.scene_name / "colmap_text"
        self.points3d_txt = self.workdir / "points3D.txt"
        self.images_txt = self.workdir / "images.txt"
        self.camera_txt = self.workdir / "cameras.txt"
        self.image_dir = self.workdir.parent / "images"


# --- Core Classes ---


# class SceneNormalizer:
#     def __init__(self, points, cfg):

#         self.cfg = cfg
#         self.points = points
#         self.scale = None
#         self.center = None

#     def filter_statistical_outliers(self, points, nb_neighbors=20, std_ratio=2.0):
#         """Filter statistical outliers using Open3D."""
#         pcd = o3d.geometry.PointCloud()
#         pcd.points = o3d.utility.Vector3dVector(points)
#         pcd, ind = pcd.remove_statistical_outlier(
#             nb_neighbors=nb_neighbors, std_ratio=std_ratio
#         )
#         filtered_points = np.asarray(pcd.points)
#         return filtered_points, ind

#     def adaptive_percentile_bounds(self, points, target_retention=0.95):
#         """
#         Adaptively determine percentile bounds based on point cloud characteristics.

#         Args:
#             points: Nx3 array of 3D points
#             target_retention: Target fraction of points to retain (0.9-0.99)

#         Returns:
#             (lower_percentile, upper_percentile): Percentile bounds
#         """
#         if len(points) < 100:
#             # For small point clouds, be more conservative
#             margin = (1.0 - target_retention) / 2.0
#             return margin * 100, (1.0 - margin) * 100

#         # Compute point density statistics
#         center = np.mean(points, axis=0)
#         distances = np.linalg.norm(points - center, axis=1)

#         # Use distance distribution to determine outlier threshold
#         median_dist = np.median(distances)
#         mad = np.median(np.abs(distances - median_dist))  # Median Absolute Deviation

#         # Adaptive bounds based on distribution spread
#         if mad < median_dist * 0.1:
#             # Tight distribution - use more aggressive filtering
#             margin = (1.0 - target_retention) / 2.0
#             return margin * 100, (1.0 - margin) * 100
#         else:
#             # Spread distribution - use conservative filtering
#             margin = (1.0 - min(target_retention + 0.02, 0.99)) / 2.0
#             return margin * 100, (1.0 - margin) * 100

#     def compute(self):
#         target_retention = self.cfg.target_retention
#         padding = self.cfg.percentile_bbox.padding
#         nb_neighbors = self.cfg.outlier_nb_neighbors
#         std_ratio = self.cfg.outlier_std_ratio

#         points = self.points
#         # First pass: statistical filtering
#         filtered_points, _ = self.filter_statistical_outliers(
#             points, nb_neighbors, std_ratio
#         )

#         # Second pass: percentile bounds on filtered points
#         lower, upper = self.adaptive_percentile_bounds(
#             filtered_points, target_retention
#         )
#         mins = np.percentile(filtered_points, lower, axis=0)
#         maxs = np.percentile(filtered_points, upper, axis=0)
#         center = (mins + maxs) / 2.0

#         ranges = maxs - mins
#         max_range = np.max(ranges)
#         scale = (2.0 * (1.0 - padding)) / max_range

#         # Test normalization
#         test_points = (points - center) * scale
#         test_range = np.max(test_points, axis=0) - np.min(test_points, axis=0)
#         max_test_range = np.max(test_range)
#         normalization_success = bool(max_test_range <= 2.1)
#         print("Robust bbox computation (hybrid)")
#         print(f"Center: [{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}]")
#         print(f"Scale: {scale:.6f}")
#         print(f"Test max range: {max_test_range:.3f}")

#         if not normalization_success:
#             print("Robust bbox computation (adaptive)")
#             lower, upper = self.adaptive_percentile_bounds(points, target_retention=0.9)
#             padding = 0.15
#             mins = np.percentile(points, lower, axis=0)
#             maxs = np.percentile(points, upper, axis=0)
#             center = (mins + maxs) / 2.0

#             # Use per-axis scaling for better cube utilization
#             ranges = maxs - mins
#             max_range = np.max(ranges)
#             scale = (2.0 * (1.0 - padding)) / max_range

#             # Test normalization
#             test_points = (points - center) * scale
#             test_range = np.max(test_points, axis=0) - np.min(test_points, axis=0)
#             max_test_range = np.max(test_range)
#             print(f"Center: [{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}]")
#             print(f"Scale: {scale:.6f}")
#             print(f"Test max range: {max_test_range:.3f}")

#         scale *= self.cfg.scale

#         return scale, center

class SceneNormalizer:
    def __init__(self, points, cfg):
        self.cfg = cfg
        self.points = points
        self.scale = None
        self.center = None

    def filter_statistical_outliers(self, points):
        """Filter statistical outliers using Open3D."""
        nb_neighbors = self.cfg.outlier_nb_neighbors
        std_ratio = self.cfg.outlier_std_ratio

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd, ind = pcd.remove_statistical_outlier(
            nb_neighbors=nb_neighbors, std_ratio=std_ratio
        )
        return np.asarray(pcd.points)

    def compute(self):
        # Unpack config
        target_retention = self.cfg.target_retention
        lower = self.cfg.percentile_bbox.lower
        upper = self.cfg.percentile_bbox.upper
        padding = self.cfg.percentile_bbox.padding
        user_scale = self.cfg.scale

        # Step 1: Remove statistical outliers
        filtered_points = self.filter_statistical_outliers(self.points)

        # Step 2: Compute bounding box percentiles
        mins = np.percentile(filtered_points, lower, axis=0)
        maxs = np.percentile(filtered_points, upper, axis=0)
        center = (mins + maxs) / 2.0

        # Step 3: Compute scale
        ranges = maxs - mins
        max_range = np.max(ranges)
        scale = (2.0 * (1.0 - padding)) / max_range

        # Step 4: Apply user-defined scale multiplier
        scale *= user_scale

        # Final normalized test range (optional check)
        test_points = (self.points - center) * scale
        test_range = np.max(test_points, axis=0) - np.min(test_points, axis=0)
        max_test_range = np.max(test_range)

        print("Robust bbox computation (config-driven)")
        print(f"Center: [{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}]")
        print(f"Scale: {scale:.6f}")
        print(f"Test max range: {max_test_range:.3f}")

        self.scale = scale
        self.center = center
        return scale, center


class PointCloud:
    def __init__(self, points3d_txt: str):
        self.points, self.rgbs = self._load_from_file(points3d_txt)

    def _load_from_file(self, path):
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        points = []
        rbgs = []
        with open(path, "r") as f:
            for line in f:
                if line.startswith("#") or line.strip() == "":
                    continue
                elems = line.strip().split()
                if len(elems) < 7:
                    continue
                x, y, z = map(float, elems[1:4])
                r, g, b = map(int, elems[4:7])
                points.append([x, y, z])
                rbgs.append([r / 255.0, g / 255.0, b / 255.0])

        print(f"Loaded {len(points)} 3D points from {path}")
        return np.array(points), np.array(rbgs)


class Camera:
    def __init__(self, camera_txt):
        self.camera = self._load_from_file(camera_txt)

    def _load_from_file(self, camera_path):
        """
        Load camera intrinsics from COLMAP cameras.txt.
        Assuming SIMPLE_RADIAL model.
        """
        with open(camera_path, "r") as f:
            for line in f:
                if line[0] == "#":
                    continue

            els = line.split(" ")
            camera = {}
            camera["w"] = int(els[2])
            camera["h"] = int(els[3])
            camera["fl_x"] = float(els[4])
            camera["fl_y"] = float(els[4])
            camera["k1"] = 0
            camera["k2"] = 0
            camera["k3"] = 0
            camera["k4"] = 0
            camera["p1"] = 0
            camera["p2"] = 0
            camera["cx"] = camera["w"] / 2
            camera["cy"] = camera["h"] / 2
            camera["is_fisheye"] = False
            if els[1] == "SIMPLE_PINHOLE":
                camera["cx"] = float(els[5])
                camera["cy"] = float(els[6])
            elif els[1] == "PINHOLE":
                camera["fl_y"] = float(els[5])
                camera["cx"] = float(els[6])
                camera["cy"] = float(els[7])
            elif els[1] == "SIMPLE_RADIAL":
                camera["cx"] = float(els[5])
                camera["cy"] = float(els[6])
                camera["k1"] = float(els[7])
            elif els[1] == "RADIAL":
                camera["cx"] = float(els[5])
                camera["cy"] = float(els[6])
                camera["k1"] = float(els[7])
                camera["k2"] = float(els[8])
            elif els[1] == "OPENCV":
                camera["fl_y"] = float(els[5])
                camera["cx"] = float(els[6])
                camera["cy"] = float(els[7])
                camera["k1"] = float(els[8])
                camera["k2"] = float(els[9])
                camera["p1"] = float(els[10])
                camera["p2"] = float(els[11])
            elif els[1] == "SIMPLE_RADIAL_FISHEYE":
                camera["is_fisheye"] = True
                camera["cx"] = float(els[5])
                camera["cy"] = float(els[6])
                camera["k1"] = float(els[7])
            elif els[1] == "RADIAL_FISHEYE":
                camera["is_fisheye"] = True
                camera["cx"] = float(els[5])
                camera["cy"] = float(els[6])
                camera["k1"] = float(els[7])
                camera["k2"] = float(els[8])
            elif els[1] == "OPENCV_FISHEYE":
                camera["is_fisheye"] = True
                camera["fl_y"] = float(els[5])
                camera["cx"] = float(els[6])
                camera["cy"] = float(els[7])
                camera["k1"] = float(els[8])
                camera["k2"] = float(els[9])
                camera["k3"] = float(els[10])
                camera["k4"] = float(els[11])

            K = np.array(
                [
                    [camera["fl_x"], 0, camera["cx"]],
                    [0, camera["fl_y"], camera["cy"]],
                    [0, 0, 1],
                ]
            )
            print(f"Loaded camera intrinsics from {camera_path}:\n{K}")
            camera["K"] = K.tolist()

        return camera


class CameraPose:
    def __init__(self, images_txt, image_dir, scale, center):
        self.frames = self._load_from_file(images_txt, image_dir, scale, center)

    def _load_from_file(
        self, pose_path: Path, image_dir: Path, scale=None, center=None
    ) -> list:
        """
        Load camera poses from COLMAP images.txt.
        Returns a dict: {'image_path', 'transform_matrix' matrix (4x4)}
        transform_matrix is the Camera-to-World transform c2w.
        """
        frames = []

        with open(pose_path, "r") as f:
            i = 0
            for line in f:
                line = line.strip()
                if line.startswith("#") or line == "":
                    continue
                i = i + 1

                if i % 2 == 1:
                    elems = line.split(" ")
                    qw, qx, qy, qz = map(float, elems[1:5])
                    tx, ty, tz = map(float, elems[5:8])
                    image_name = elems[9]

                    # Convert to rotation matrix
                    rot = R.from_quat([qx, qy, qz, qw]).as_matrix()
                    tvec = np.array([tx, ty, tz])

                    # World-to-Camera transform
                    w2c = np.eye(4)
                    w2c[:3, :3] = rot
                    w2c[:3, 3] = tvec
                    # Invert to get Camera-to-World transform
                    c2w = np.linalg.inv(w2c)

                    # Apply scaling and centering if provided
                    if scale is not None and center is not None:
                        # Scale and center the translation vector
                        c2w[:3, 3] = scale * (c2w[:3, 3] - center)

                    pose = {
                        "file_path": str(image_dir / image_name),
                        "transform_matrix": c2w.tolist(),
                    }
                    frames.append(pose)

        print(f"Loaded {len(frames)} camera poses from {pose_path}")
        return frames


class ColmapScene:
    def __init__(self, cfg):
        self.cfg = cfg
        self.scene_paths = ScenePaths(self.cfg.scene_name)
        self.cam = Camera(self.scene_paths.camera_txt)
        self.pc = PointCloud(self.scene_paths.points3d_txt)

        self.scene_norm = SceneNormalizer(self.pc.points, self.cfg)
        self.scale, self.center = self.scene_norm.compute()
        
        self.cam_pos = CameraPose(
            self.scene_paths.images_txt,
            self.scene_paths.image_dir,
            self.scale,
            self.center,
        )

    def normalize_pts(self):
        return (self.pc.points - self.center) * self.scale


# helper methods


def validate_camera_orientations_detailed(frames, points):
    """
    Validate that cameras are oriented correctly after transformation.
    Check that:
    1. Cameras look toward the scene (negative Z direction)
    2. +Z axis points away from scene center (opposite to viewing direction)
    """
    print("=== Camera Orientation Validation ===")
    
    # Compute scene center
    scene_center = np.mean(points, axis=0)
    print(f"Scene center: [{scene_center[0]:.3f}, {scene_center[1]:.3f}, {scene_center[2]:.3f}]")
    
    valid_orientations = 0
    total_cameras = len(frames)
    
    viewing_directions = []
    z_directions = []
    
    for i, frame in enumerate(frames):
        T = np.array(frame["transform_matrix"])
        camera_position = T[:3, 3]
        
        # Camera's local coordinate axes in world space
        camera_x = T[:3, 0]  # Right
        camera_y = T[:3, 1]  # Up (after coordinate flip, should be up)
        camera_z = T[:3, 2]  # Forward axis (cameras look in -Z direction)
        
        # Camera viewing direction (where camera is looking)
        viewing_direction = -camera_z  # Cameras look in negative Z direction
        
        # Direction from camera to scene center
        to_scene = scene_center - camera_position
        to_scene_normalized = to_scene / np.linalg.norm(to_scene)
        
        # Check if camera is looking toward scene
        cos_angle = np.dot(viewing_direction, to_scene_normalized)
        angle_degrees = np.arccos(np.clip(cos_angle, -1, 1)) * 180 / np.pi
        
        viewing_directions.append(viewing_direction)
        z_directions.append(camera_z)
        
        if angle_degrees < 90:  # Camera looking toward scene
            valid_orientations += 1
            status = "✓"
        else:
            status = "✗"
            
        if i < 5:  # Print details for first 5 cameras
            print(f"Camera {i}: {status} Angle to scene: {angle_degrees:.1f}°")
            print(f"  Position: [{camera_position[0]:.3f}, {camera_position[1]:.3f}, {camera_position[2]:.3f}]")
            print(f"  Viewing dir: [{viewing_direction[0]:.3f}, {viewing_direction[1]:.3f}, {viewing_direction[2]:.3f}]")
            print(f"  +Z axis: [{camera_z[0]:.3f}, {camera_z[1]:.3f}, {camera_z[2]:.3f}]")
    
    # Compute mean viewing direction and mean +Z direction
    mean_viewing = np.mean(viewing_directions, axis=0)
    mean_z = np.mean(z_directions, axis=0)
    
    print(f"\nMean viewing direction: [{mean_viewing[0]:.3f}, {mean_viewing[1]:.3f}, {mean_viewing[2]:.3f}]")
    print(f"Mean +Z direction: [{mean_z[0]:.3f}, {mean_z[1]:.3f}, {mean_z[2]:.3f}]")
    
    # Check if +Z points opposite to viewing direction
    dot_product = np.dot(mean_viewing, mean_z)
    print(f"Dot product (viewing · +Z): {dot_product:.3f}")
    print(f"Expected: close to -1 (opposite directions)")
    
    orientation_ratio = valid_orientations / total_cameras
    print(f"\nCameras oriented toward scene: {valid_orientations}/{total_cameras} ({orientation_ratio:.1%})")
    
    # Validation results
    z_opposite_check = dot_product < -0.8  # Should be close to -1
    orientation_check = orientation_ratio > 0.8  # At least 80% should look toward scene
    
    print(f"\n=== Validation Results ===")
    print(f"Z-axis opposite to viewing direction: {'✓' if z_opposite_check else '✗'}")
    print(f"Cameras looking toward scene: {'✓' if orientation_check else '✗'}")
    
    return z_opposite_check and orientation_check


def validate_coordinate_system(frames, points):
    """
    Validate the coordinate system conventions.
    """
    print("\n=== Coordinate System Validation ===")
    
    # Check point cloud bounds
    min_coords = np.min(points, axis=0)
    max_coords = np.max(points, axis=0)
    
    print(f"Point cloud bounds:")
    print(f"  X: [{min_coords[0]:.3f}, {max_coords[0]:.3f}]")
    print(f"  Y: [{min_coords[1]:.3f}, {max_coords[1]:.3f}]")
    print(f"  Z: [{min_coords[2]:.3f}, {max_coords[2]:.3f}]")
    
    # Check camera positions
    camera_positions = np.array([np.array(f["transform_matrix"])[:3, 3] for f in frames])
    cam_min = np.min(camera_positions, axis=0)
    cam_max = np.max(camera_positions, axis=0)
    
    print(f"Camera position bounds:")
    print(f"  X: [{cam_min[0]:.3f}, {cam_max[0]:.3f}]")
    print(f"  Y: [{cam_min[1]:.3f}, {cam_max[1]:.3f}]")
    print(f"  Z: [{cam_min[2]:.3f}, {cam_max[2]:.3f}]")
    
    # Check if cameras are outside the point cloud (looking inward)
    scene_center = np.mean(points, axis=0)
    camera_center = np.mean(camera_positions, axis=0)
    
    print(f"Scene center: [{scene_center[0]:.3f}, {scene_center[1]:.3f}, {scene_center[2]:.3f}]")
    print(f"Camera center: [{camera_center[0]:.3f}, {camera_center[1]:.3f}, {camera_center[2]:.3f}]")
    
    # Distance from camera center to scene center
    distance = np.linalg.norm(camera_center - scene_center)
    print(f"Distance camera center to scene center: {distance:.3f}")
    
    return True


def average_camera_rotation(frames):
    R_accum = np.zeros((3, 3))
    for f in frames:
        pose = np.array(f["transform_matrix"])
        R_accum += pose[:3, :3]

    # Durchschnitt berechnen
    R_avg = R_accum / len(frames)

    # SVD, um gültige Rotationsmatrix zu extrahieren
    U, _, Vt = np.linalg.svd(R_avg)
    R_mean = U @ Vt

    # Falls Determinante -1 (Reflexion), korrigieren
    if np.linalg.det(R_mean) < 0:
        U[:, -1] *= -1
        R_mean = U @ Vt

    return R_mean


def compute_mean_forward_direction(frames):
    """
    FIXED: Compute mean forward direction using negative Z-axis (COLMAP convention)
    In COLMAP, cameras look in the negative Z direction of their local coordinate system.
    """
    # Use negative Z-axis for forward direction (COLMAP convention)
    forward_dirs = np.array([-np.array(f["transform_matrix"])[:3, 2] for f in frames])
    mean_forward = forward_dirs.mean(axis=0)
    return mean_forward / np.linalg.norm(mean_forward)


def rotation_between_vectors(a, b):
    """Compute rotation matrix to align vector a with vector b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    
    # Handle the case where vectors are already aligned
    if np.allclose(a, b):
        return np.eye(3)
    
    # Handle the case where vectors are opposite
    if np.allclose(a, -b):
        # Find a perpendicular vector
        if abs(a[0]) < 0.9:
            perp = np.array([1, 0, 0])
        else:
            perp = np.array([0, 1, 0])
        # Create perpendicular vector
        axis = np.cross(a, perp)
        axis = axis / np.linalg.norm(axis)
        return R.from_rotvec(np.pi * axis).as_matrix()
    
    # General case using Rodrigues' rotation formula
    v = np.cross(a, b)
    c = np.dot(a, b)
    s = np.linalg.norm(v)
    
    if s < 1e-8:  # Vectors are parallel
        return np.eye(3)
    
    kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + kmat + (kmat @ kmat) * ((1 - c) / (s**2))


def apply_world_rotation(frames, points, R_align):
    """
    FIXED: Apply world rotation correctly to camera-to-world matrices.
    For c2w matrices, the transformation is: T_new = R_align_4x4 @ T_old
    """
    # Convert 3x3 rotation matrix to 4x4 transformation matrix
    R_align_4x4 = np.eye(4)
    R_align_4x4[:3, :3] = R_align
    
    new_frames = []
    for f in frames:
        T = np.array(f["transform_matrix"])
        # Correct transformation for camera-to-world matrices
        T_new = R_align_4x4 @ T
        new_frames.append({**f, "transform_matrix": T_new.tolist()})

    # Transform points consistently
    new_points = points @ R_align.T
    return new_frames, new_points


def flip_colmap2nerf(points, frames, shift=[0, 0, 0]):
    """
    FIXED: COLMAP to NeRF coordinate transformation
    Properly handle the coordinate system flip for camera-to-world matrices.
    """
    # Coordinate transformation matrix: flip Y and Z axes
    flip = np.diag([1, -1, -1])
    
    # Transform 3D points
    points_transformed = points @ flip.T + shift

    # Transform camera poses correctly for c2w matrices
    for pose in frames:
        T = np.array(pose["transform_matrix"])
        
        # For camera-to-world matrices, apply: T_new = flip @ T @ flip.T
        # This correctly transforms both rotation and translation
        T_transformed = np.eye(4)
        T_transformed[:3, :3] = flip @ T[:3, :3] @ flip.T
        T_transformed[:3, 3] = flip @ T[:3, 3] + shift
        
        pose["transform_matrix"] = T_transformed.tolist()

    return points_transformed, frames


def compute_scene_aabb(
    points, aabb_adjust, percentile_bounds=(1.0, 99.0), padding=0.02, cfg=None
):
    """
    Compute the Axis-Aligned Bounding Box (AABB) of the scene points.

    Args:
        points: Nx3 array of 3D points in normalized coordinates
        percentile_bounds: (lower, upper) percentiles for robust bounds computation
        padding: Additional padding around the AABB (as fraction of range)

    Returns:
        dict: AABB information with min/max bounds and metadata
    """
    if len(points) == 0:
        raise ValueError("Cannot compute AABB for empty point cloud")

    # Compute robust bounds using percentiles
    lower_percentile, upper_percentile = percentile_bounds
    aabb_min = np.percentile(points, lower_percentile, axis=0)
    aabb_max = np.percentile(points, upper_percentile, axis=0)

    # Add padding
    if padding > 0:
        ranges = aabb_max - aabb_min
        padding_amount = ranges * padding
        aabb_min -= padding_amount
        aabb_max += padding_amount

    # Ensure AABB is within the normalized cube [-1, 1]³
    aabb_min = np.maximum(aabb_min, -1.0)
    aabb_max = np.minimum(aabb_max, 1.0)

    # Compute additional metadata
    center = (aabb_min + aabb_max) / 2.0
    size = aabb_max - aabb_min
    volume = np.prod(size)

    # Compute efficiency metrics
    cube_volume = 8.0  # Volume of [-1,1]³ cube
    volume_efficiency = volume / cube_volume

    # Store original bounds for reference
    remove_below = aabb_min[2]
    remove_above = aabb_max[2]
    
    # Apply AABB adjustments based on configuration
    if cfg and cfg.get("remove_below_aabb", True):
        aabb_min = np.array([-1, -1, aabb_min[2]]) + np.array(aabb_adjust["aabb_min"])
    else:
        aabb_min = np.array([-1, -1, -1]) + np.array(aabb_adjust["aabb_min"])
    
    if cfg and cfg.get("remove_upper_aabb", True):
        z_offset = 0.1
        z_axis = aabb_max[2] + z_offset
        z_axis = 1 if z_axis > 1 else z_axis
        aabb_max = np.array([1, 1, z_axis]) + np.array(aabb_adjust["aabb_max"])
    else:    
        aabb_max = np.array([1, 1, 1]) + np.array(aabb_adjust["aabb_max"])

    aabb_info = {
        "aabb_remove_below": remove_below,
        "aabb_remove_above": remove_above,
        "aabb_min": aabb_min.tolist(),
        "aabb_max": aabb_max.tolist(),
        "aabb_center": center.tolist(),
        "aabb_size": size.tolist(),
        "aabb_volume": float(volume),
        "volume_efficiency": float(volume_efficiency),
        "percentile_bounds": percentile_bounds,
        "padding": float(padding),
        "num_points": len(points),
    }

    print(f"Scene AABB computed:")
    print(f"  Min bounds: [{aabb_min[0]:.3f}, {aabb_min[1]:.3f}, {aabb_min[2]:.3f}]")
    print(f"  Max bounds: [{aabb_max[0]:.3f}, {aabb_max[1]:.3f}, {aabb_max[2]:.3f}]")
    print(f"  Center: [{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}]")
    print(f"  Size: [{size[0]:.3f}, {size[1]:.3f}, {size[2]:.3f}]")
    print(f"  Volume efficiency: {volume_efficiency:.1%} of full cube")

    return aabb_info


def draw_cube():
    # [x, y, z]
    return np.array(
        [
            [1, -1, -1],
            [1, 1, -1],
            [1, 1, -1],
            [-1, 1, -1],
            [-1, 1, -1],
            [-1, -1, -1],
            [-1, -1, -1],
            [1, -1, -1],
            [1, -1, 1],
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, -1],
            [1, 1, 1],
            [1, -1, 1],
            [1, -1, 1],
            [-1, -1, 1],
            [-1, -1, 1],
            [-1, 1, 1],
            [-1, 1, 1],
            [1, 1, 1],
            [1, 1, 1],
            [-1, 1, 1],
            [-1, 1, 1],
            [-1, 1, -1],
            [-1, 1, -1],
            [-1, -1, -1],
            [-1, -1, -1],
            [-1, -1, 1],
        ]
    )


def draw_aabb(aabb_min, aabb_max):
    """
    Generate line segments for visualizing an AABB.

    Args:
        aabb_min: [x_min, y_min, z_min]
        aabb_max: [x_max, y_max, z_max]

    Returns:
        Array of line segments for AABB visualization
    """
    x_min, y_min, z_min = aabb_min
    x_max, y_max, z_max = aabb_max

    # Define the 8 corners of the AABB
    corners = np.array(
        [
            [x_min, y_min, z_min],  # 0
            [x_max, y_min, z_min],  # 1
            [x_max, y_max, z_min],  # 2
            [x_min, y_max, z_min],  # 3
            [x_min, y_min, z_max],  # 4
            [x_max, y_min, z_max],  # 5
            [x_max, y_max, z_max],  # 6
            [x_min, y_max, z_max],  # 7
        ]
    )

    # Define the 12 edges of the AABB
    edges = [
        # Bottom face
        [0, 1],
        [1, 2],
        [2, 3],
        [3, 0],
        # Top face
        [4, 5],
        [5, 6],
        [6, 7],
        [7, 4],
        # Vertical edges
        [0, 4],
        [1, 5],
        [2, 6],
        [3, 7],
    ]

    # Create line segments
    lines = []
    for edge in edges:
        lines.extend([corners[edge[0]], corners[edge[1]]])

    return np.array(lines)


def display_points(
    points,
    rgbs=None,
    poses=None,
    aabb_info=None,
    shift=[0, 0, 0],
    size=7,
    clip_to_unit_cube=False,
):
    """
    Display a 3D point cloud with camera poses and AABB using VisPy.

    FIXED: Corrected camera forward direction visualization.
    ADDED: AABB visualization support.

    Parameters:
        points: Nx3 array of 3D points.
        rgbs: Nx3 array of RGB colors for each point (optional).
        poses: List of camera poses, each a dict with 'transform_matrix' (4x4 matrix).
        aabb_info: AABB information dictionary (optional).
        shift: Translation to apply to the point cloud.
    """

    points = points + np.array(shift)
    canvas = scene.SceneCanvas(keys="interactive", show=True, bgcolor="black")
    view = canvas.central_widget.add_view()
    view.camera = scene.cameras.ArcballCamera(fov=45, distance=3)

    # Draw point cloud
    scatter = visuals.Markers()

    if rgbs is not None and len(rgbs) == len(points):
        scatter.set_data(
            points, face_color=rgbs, size=size, edge_color=None, symbol="o"
        )
    else:
        scatter.set_data(
            points, face_color="blue", size=size, edge_color="black", symbol="o"
        )

    view.add(scatter)

    # Draw camera poses
    if poses is not None:
        for pose in poses:
            T = np.array(pose["transform_matrix"])
            origin = T[:3, 3]
            # FIXED: Use negative Z-axis for forward direction (COLMAP convention)
            forward = -T[:3, 2] * 0.1  # Forward camera vector is -Z-axis
            up = T[:3, 1] * 0.05  # Up vector is Y-axis
            right = T[:3, 0] * 0.05  # Right vector is X-axis

            frustum_lines = np.array(
                [origin, origin + forward, origin, origin + up, origin, origin + right]
            )

            colors = np.array(
                [
                    [0, 0, 1],  # Z (forward) → blue
                    [0, 0, 1],
                    [0, 1, 0],  # Y (up) → green
                    [0, 1, 0],
                    [1, 0, 0],  # X (right) → red
                    [1, 0, 0],
                ]
            )

            frustum = visuals.Line(
                pos=frustum_lines, color=colors, method="gl", width=2
            )
            view.add(frustum)

    # Add axis & unit cube
    axis = scene.visuals.XYZAxis(parent=view.scene)
    cube_lines = draw_cube()

    cube = visuals.Line(pos=cube_lines, color="red", method="gl", width=6)
    view.add(cube)

    # Draw AABB if provided
    if aabb_info is not None:
        aabb_min = np.array(aabb_info["aabb_min"]) + np.array(shift)
        aabb_max = np.array(aabb_info["aabb_max"]) + np.array(shift)
        aabb_lines = draw_aabb(aabb_min, aabb_max)

        aabb_visual = visuals.Line(pos=aabb_lines, color="green", method="gl", width=4)
        view.add(aabb_visual)

        print(f"AABB visualization added (green box)")

    # Define key press event
    @canvas.events.key_press.connect
    def on_key_press(event):
        if event.key == "R":
            transform_matrix = view.camera.transform.matrix
            rotation_matrix = transform_matrix[:3, :3]
            print("Current Rotation Matrix (on 'R'):\n", rotation_matrix)
            # Convert to Python list of lists (for YAML)
            print("\nRotation_initial:")
            for row in rotation_matrix:
                formatted_row = ", ".join(f"{val: .8f}" for val in row)
                print(f"  - [{formatted_row}]")

    app.run()


def write_transform_to_json(transform, output_path):
    """
    Write the transform dictionary to a JSON file.
    """
    with open(output_path, "w") as f:
        json.dump(transform, f, indent=4)

    print(f"Transform saved to {output_path}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cfg_path",
        type=str,
        default=None,
        required=True,
        help="Path to the configuration YAML file",
    )
    return parser.parse_args()


def load_cfg(args):
    cfg = OmegaConf.load(args.cfg_path)
    return cfg


def main():
    """
    FIXED: Main function with corrected transformation pipeline.
    The transformations are now applied in the correct order with proper
    mathematical operations for camera-to-world matrices.
    """
    args = parse_args()
    cfg = load_cfg(args)

    colmap_scene = ColmapScene(cfg)
    frames = colmap_scene.cam_pos.frames
    points_norm = colmap_scene.normalize_pts()
    rgbs = colmap_scene.pc.rgbs
    
    # FIXED: Compute mean forward direction using correct COLMAP convention
    mean_forward = compute_mean_forward_direction(frames)
    # CORRECTED: Align viewing direction with -Z so that +Z points opposite to viewing direction
    target_z = np.array([0, 0, -1])  # Negative Z so +Z points opposite to viewing direction
    R_align = rotation_between_vectors(mean_forward, target_z)
    
    # FIXED: Apply world rotation correctly
    frames, points_norm = apply_world_rotation(frames, points_norm, R_align)
    
    # FIXED: Apply coordinate system flip correctly
    points_norm, frames = flip_colmap2nerf(points_norm, frames, cfg.shift)
    
    # Validate transformations
    print("\n" + "="*60)
    print("VALIDATING TRANSFORMATIONS")
    print("="*60)
    validate_coordinate_system(frames, points_norm)
    validation_passed = validate_camera_orientations_detailed(frames, points_norm)
    
    if validation_passed:
        print("\n✓ All validations PASSED - Transformations appear correct!")
    else:
        print("\n✗ Some validations FAILED - Please review the transformations!")
    print("="*60)
    
    print("Computing scene AABB...")
    aabb_info = compute_scene_aabb(
        points_norm,
        aabb_adjust=cfg.aabb_adjust,
        percentile_bounds=(1.0, 99.0),
        padding=0.02,
        cfg=cfg
    )
    
    intrinsics = colmap_scene.cam.camera
    center = colmap_scene.center
    scale = colmap_scene.scale
    
    transform = {
        **intrinsics,
        "frames": frames,
        "scene_aabb": aabb_info,
        "normalization": {
            "center": center.tolist(),
            "scale": float(scale),
        },
    }

    output_path = Path(f"transforms_{cfg.scene_name}.json")
    write_transform_to_json(transform, output_path)

    print(f"\nSummary:")
    print(f"  Total 3D points: {len(colmap_scene.pc.points)}")
    print(f"  Camera poses: {len(frames)}")
    print(f"  Scene AABB volume efficiency: {aabb_info['volume_efficiency']:.1%}")
    print(f"  Transform saved to: {output_path}")

    if cfg.visualize:
        display_points(points_norm, rgbs, frames, aabb_info)


if __name__ == "__main__":
    main()

