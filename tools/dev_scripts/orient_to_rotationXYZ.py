#!/usr/bin/env python3
"""
Final robust converter:
- Replace xformOp:orient* (including suffix) by xformOp:rotateXYZ* (matching USD rotationXYZ semantics)
- For each prim/time: compute the prim's local matrix, extract quaternion, convert quaternion -> intrinsic XYZ Euler (degrees)
- Insert the newly created rotate op into xformOpOrder at the same index as the original orient token
- Unwrap Euler sequence to avoid 360° jumps
- Keeps other ops unchanged

Usage:
    python orient_to_rotationXYZ_intrinsic.py input.usda output.usda
"""

import sys, math
from pxr import Usd, UsdGeom, Gf, Sdf

# ---------- math helpers ----------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def quat_to_intrinsic_xyz_degrees(quat):
    """
    Convert quaternion (Gf.Quat* or tuple-like) to intrinsic XYZ Euler angles in degrees.
    The quaternion is interpreted as (w, x, y, z).
    Returns (X_deg, Y_deg, Z_deg).
    Formulas derived from intrinsic rotation R = Rx(X) * Ry(Y) * Rz(Z).
    """
    # normalize / extract components
    if hasattr(quat, "real") and hasattr(quat, "imaginary"):
        w = float(quat.real)
        x = float(quat.imaginary[0])
        y = float(quat.imaginary[1])
        z = float(quat.imaginary[2])
    else:
        seq = list(quat)
        if len(seq) != 4:
            raise ValueError("Quaternion must have 4 components")
        # attempt to detect ordering (w,x,y,z) or (x,y,z,w)
        w_first = abs(seq[0])
        w_last = abs(seq[3])
        if w_last > w_first:
            x, y, z, w = seq
        else:
            w, x, y, z = seq
        w = float(w); x = float(x); y = float(y); z = float(z)

    # Normalize quaternion to guard against tiny numerical drift
    norm = math.sqrt(w*w + x*x + y*y + z*z)
    if norm == 0.0:
        raise ValueError("Zero-length quaternion")
    w /= norm; x /= norm; y /= norm; z /= norm

    # intrinsic XYZ conversion (from quaternion to angles for R = Rx * Ry * Rz)
    # Using standard relations for intrinsic Tait-Bryan angles (X then Y then Z)
    # Reference formulas:
    # sinY = 2*(w*y - z*x)
    # Y = asin(sinY)
    # X = atan2(2*(w*x + y*z), 1 - 2*(x^2 + y^2))
    # Z = atan2(2*(w*z + x*y), 1 - 2*(y^2 + z^2))
    sinY = 2.0 * (w*y - z*x)
    sinY = clamp(sinY, -1.0, 1.0)
    Y = math.asin(sinY)

    Xnum = 2.0 * (w*x + y*z)
    Xden = 1.0 - 2.0 * (x*x + y*y)
    X = math.atan2(Xnum, Xden)

    Znum = 2.0 * (w*z + x*y)
    Zden = 1.0 - 2.0 * (y*y + z*z)
    Z = math.atan2(Znum, Zden)

    # convert to degrees
    rad2deg = 180.0 / math.pi
    return (X * rad2deg, Y * rad2deg, Z * rad2deg)

# ---------- USD helper functions ----------
def gather_prim_sample_times(prim):
    """
    Collect numeric times (floats) for a prim by checking authored time samples
    of its attributes. If at least one transform-related attribute has only
    default values, ensure we include a single None marker so default is sampled.
    """
    times_set = set()
    has_default_only = False
    for a in prim.GetAttributes():
        if a.HasAuthoredValue():
            try:
                ts = a.GetTimeSamples()
            except Exception:
                ts = a.GetTimeSamples() if hasattr(a, "GetTimeSamples") else []
            if ts:
                for t in ts:
                    try:
                        times_set.add(float(t))
                    except Exception:
                        pass
            else:
                has_default_only = True
    times = sorted(times_set)
    if has_default_only and not times:
        return [None]
    return times

def decompose_local_rotation_euler(xformable, time_code):
    """
    Return intrinsic XYZ Euler (degrees) from prim's local matrix at the given time_code.
    time_code: None or numeric (float)
    """
    # obtain local matrix robustly
    try:
        if time_code is None:
            m = xformable.GetLocalTransformation()
        else:
            m = xformable.GetLocalTransformation(Usd.TimeCode(time_code))
    except TypeError:
        # some bindings require explicit TimeCode.Default()
        if time_code is None:
            m = xformable.GetLocalTransformation(Usd.TimeCode.Default())
        else:
            m = xformable.GetLocalTransformation(Usd.TimeCode(time_code))
    except Exception as e:
        raise

    # attempt to orthonormalize if available
    try:
        m.Orthonormalize()
    except Exception:
        pass

    # Extract a quaternion from matrix (robust path)
    try:
        quat = m.ExtractRotationQuat()
    except Exception:
        try:
            rot = m.ExtractRotation()
            angs = rot.Decompose(Gf.Vec3d(1,0,0), Gf.Vec3d(0,1,0), Gf.Vec3d(0,0,1))
            return (float(angs[0]), float(angs[1]), float(angs[2]))
        except Exception as e:
            raise

    # Convert to intrinsic XYZ Euler using the quaternion conversion above
    return quat_to_intrinsic_xyz_degrees(quat)

def unwrap_angles_sequence(seq):
    """
    seq: list of (x,y,z) tuples in degrees.
    Returns unwrapped list where each component changes continuously (minimizes jumps >180).
    """
    if not seq:
        return []
    out = [list(seq[0])]
    for cur in seq[1:]:
        prev = out[-1]
        un = []
        for p, c in zip(prev, cur):
            diff = c - p
            while diff <= -180.0:
                diff += 360.0
            while diff > 180.0:
                diff -= 360.0
            un.append(p + diff)
        out.append(un)
    return out

# ---------- main conversion ----------
def convert_stage_intrinsic(input_path, output_path):
    stage = Usd.Stage.Open(input_path)
    if stage is None:
        raise RuntimeError("Failed to open stage: %s" % input_path)

    # Traverse prims
    for prim in stage.Traverse():
        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            continue

        # collect orient attributes (exact or suffix)
        orient_names = []
        for a in prim.GetAttributes():
            n = a.GetName()
            if n == "xformOp:orient" or n.startswith("xformOp:orient:"):
                if a.HasAuthoredValue():
                    orient_names.append(n)
        if not orient_names:
            continue

        # gather sample times for this prim so local matrix sampling is correct
        times = gather_prim_sample_times(prim)  # list of floats or [None]

        # get existing xformOpOrder (if any)
        order_attr = prim.GetAttribute("xformOpOrder")
        current_order = None
        if order_attr and order_attr.HasAuthoredValue():
            try:
                current_order = list(order_attr.Get())
            except Exception:
                current_order = None

        # process each orient attr
        for orient_name in orient_names:
            orient_attr = prim.GetAttribute(orient_name)
            if not orient_attr or not orient_attr.HasAuthoredValue():
                continue

            # derive suffix for rotate op
            parts = orient_name.split(':')
            suffix = ""
            if len(parts) > 2:
                suffix = ":".join(parts[2:])
            api_suffix = "rotationXYZ" + ((":" + suffix) if suffix else "")

            # create rotate op (AddRotateXYZOp) with same suffix
            rotOp = xformable.AddRotateXYZOp(UsdGeom.XformOp.PrecisionFloat, api_suffix, False)
            rot_attr = rotOp.GetAttr()
            if not rot_attr:
                print("WARNING: could not create rotate op on", prim.GetPath(), orient_name)
                continue

            # figure out insertion index in xformOpOrder (first occurrence)
            insert_index = None
            if current_order is not None:
                try:
                    insert_index = current_order.index(orient_name)
                except ValueError:
                    insert_index = None

            # compute Euler samples by decomposing local matrix at each time
            sample_eulers = []
            sample_times_order = []
            for t in times:
                time_code = None if t is None else float(t)
                try:
                    euler = decompose_local_rotation_euler(xformable, time_code)
                except Exception as e:
                    print("ERROR decomposing rotation for prim %s time %s: %s" % (prim.GetPath(), str(time_code), e))
                    euler = None
                sample_eulers.append(euler)
                sample_times_order.append(time_code)

            # filter out None entries (shouldn't happen often)
            valid_pairs = [(ti, e) for ti, e in zip(sample_times_order, sample_eulers) if e is not None]
            if not valid_pairs:
                # nothing to write
                continue

            # unwrap sequence
            times_list = [p[0] for p in valid_pairs]
            euler_list = [p[1] for p in valid_pairs]
            unwrapped = unwrap_angles_sequence(euler_list)

            # write back to rot_attr with same time ordering
            for (time_code, _), e in zip(valid_pairs, unwrapped):
                tup = (float(e[0]), float(e[1]), float(e[2]))
                if time_code is None:
                    rot_attr.Set(tup)
                else:
                    rot_attr.Set(tup, time_code)

            # find exact created attribute token/name from rot_attr if possible
            try:
                created_token = rot_attr.GetName()
            except Exception:
                # fallback search
                created_token = None
                for a in prim.GetAttributes():
                    an = a.GetName()
                    if an.startswith("xformOp:rotateXYZ"):
                        created_token = an
                        break
                if created_token is None:
                    created_token = "xformOp:rotateXYZ" + ((":" + suffix) if suffix else "")

            # update xformOpOrder: insert created_token at same index => replace orient_name there
            if current_order is None:
                # create new order containing only the created token (safe fallback)
                prim.CreateAttribute("xformOpOrder", Sdf.ValueTypeNames.TokenArray).Set([created_token])
                current_order = [created_token]
            else:
                new_order = list(current_order)
                if insert_index is not None:
                    # replace the orient token at that index with the created token
                    new_order[insert_index:insert_index+1] = [created_token]
                else:
                    # orient token not found in order: insert created_token at front (fallback)
                    new_order.insert(0, created_token)
                order_attr.Set(new_order)
                current_order = new_order

            # clear original orient authored values
            orient_attr.Clear()

    # export result
    root = stage.GetRootLayer()
    if not root:
        raise RuntimeError("No root layer found.")
    root.Export(output_path)
    print("Exported to:", output_path)

# ---------- entry ----------
def main():
    if len(sys.argv) != 3:
        print("Usage: python orient_to_rotationXYZ_intrinsic.py input.usda output.usda")
        sys.exit(1)
    convert_stage_intrinsic(sys.argv[1], sys.argv[2])

if __name__ == "__main__":
    main()
