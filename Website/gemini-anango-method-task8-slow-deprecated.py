def transform_points_spherical_aberration_t8(x_o_flat, y_o_flat, R_mirror):
    x_i_flat = np.full_like(x_o_flat, np.nan)
    y_i_flat = np.full_like(y_o_flat, np.nan)
    if R_mirror <= 1e-6: return x_i_flat, y_i_flat

    at_C_mask = np.isclose(x_o_flat, 0) & np.isclose(y_o_flat, 0)
    x_i_flat[at_C_mask], y_i_flat[at_C_mask] = 0, 0
    
    on_axis_mask = ~at_C_mask & np.isclose(y_o_flat, 0)
    if np.any(on_axis_mask):
        x_o_ax = x_o_flat[on_axis_mask]
        den_ax = R_mirror + 2 * x_o_ax 
        x_i_ax = np.full_like(x_o_ax, np.nan)
        safe_ax = ~np.isclose(den_ax, 0)
        x_i_ax[safe_ax] = -x_o_ax[safe_ax] * R_mirror / den_ax[safe_ax] 
        x_i_flat[on_axis_mask], y_i_flat[on_axis_mask] = x_i_ax, 0
    
    general_mask = ~at_C_mask & ~on_axis_mask
    if np.any(general_mask):
        x_o_gen, y_o_gen = x_o_flat[general_mask], y_o_flat[general_mask]
        x_i_calc, y_i_calc = np.full_like(x_o_gen, np.nan), np.full_like(y_o_gen, np.nan)
        
        valid_y_mask = (y_o_gen**2 <= R_mirror**2 + 1e-9)
        if np.any(valid_y_mask):
            x_o_v, y_o_v = x_o_gen[valid_y_mask], y_o_gen[valid_y_mask]
            y_m = y_o_v
            sqrt_arg = R_mirror**2 - y_m**2
            safe_sqrt_mask = sqrt_arg >= -1e-9
            
            if np.any(safe_sqrt_mask):
                x_o_s, y_o_s, y_m_s = x_o_v[safe_sqrt_mask], y_o_v[safe_sqrt_mask], y_m[safe_sqrt_mask]
                x_m_s = -np.sqrt(np.maximum(0, sqrt_arg[safe_sqrt_mask]))

                L_inc_x, N_unit_x, N_unit_y = -1.0, x_m_s / R_mirror, y_m_s / R_mirror
                dot_L_N = L_inc_x * N_unit_x
                L_rfl_x, L_rfl_y = L_inc_x - 2 * dot_L_N * N_unit_x, -2 * dot_L_N * N_unit_y
                
                numerator_t = x_o_s * y_m_s - y_o_s * x_m_s
                denominator_t = L_rfl_x * y_o_s - L_rfl_y * x_o_s
                
                t_intersect = np.full_like(x_o_s, np.nan)
                safe_intersect_mask = ~np.isclose(denominator_t, 0)
                t_intersect[safe_intersect_mask] = numerator_t[safe_intersect_mask] / denominator_t[safe_intersect_mask]
                
                x_i_temp, y_i_temp = x_m_s + t_intersect * L_rfl_x, y_m_s + t_intersect * L_rfl_y
                
                x_i_valid_y, y_i_valid_y = np.full_like(x_o_v, np.nan), np.full_like(y_o_v, np.nan)
                x_i_valid_y[safe_sqrt_mask], y_i_valid_y[safe_sqrt_mask] = x_i_temp, y_i_temp
                x_i_calc[valid_y_mask], y_i_calc[valid_y_mask] = x_i_valid_y, y_i_valid_y
        x_i_flat[general_mask], y_i_flat[general_mask] = x_i_calc, y_i_calc
    return x_i_flat, y_i_flat