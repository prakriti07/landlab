# -*- coding: utf-8 -*-
"""
This is an implementation of Vaughan Voller's experimental boundary method
reduced complexity flow router. Credit: Voller, Hobley, Paola.

Created on Fri Feb 20 09:32:27 2015

@author: danhobley (SiccarPoint), after volle001@umn.edu
"""

import numpy as np
from landlab import RasterModelGrid, Component, FieldError, INACTIVE_LINK, \
    CLOSED_BOUNDARY, CORE_NODE
import inspect
from landlab.utils.decorators import use_file_name_or_kwds


class DischargeDiffuser(Component):
    """Diffuse sediment proportional to an implicit water discharge value.

    This class implements Voller, Hobley, and Paola's scheme for sediment
    diffusion, where the diffusivity of the sediment is proportional to the
    local discharge of water. The method works by solving for a potential
    field describing the water discharge at all nodes on the grid, which
    enforces both mass conservation and flow downhill along topographic
    gradients. This routine is designed to construct sediment fans.

    Note that both the water and sediment discharges are calculated together
    within the component.

    The algorithm uses a rule that looks like:

        q_sed = q_water * (S - S_crit)

    where S_crit is a critical slope threshold. [MODIFY THIS]

    It is VITAL you initialize this component AFTER setting boundary
    conditions.

    The primary method of this class is :func:`run_one_step`.

    Construction::

        DischargeDiffuser(grid, ...)

    Notes
    -----
    This is a "research grade" component, and is subject to dramatic change
    with little warning. No guarantees are made regarding its accuracy or
    utility. It is not recommended for user use yet!

    Parameters
    ----------
    grid : ModelGrid
        A grid.


    Examples
    --------
    >>> from landlab import HexModelGrid
    >>> import numpy as np
    >>> mg = HexModelGrid(4, 6, dx=2., shape='rect', orientation='vertical')
    >>> z = mg.add_zeros('node', 'topographic__elevation')
    >>> Q_in = mg.add_ones('node', 'water__unit_flux_in')
    >>> z += mg.node_y.copy()
    >>> potfr = PotentialityFlowRouter(mg)
    >>> potfr.run_one_step()
    >>> Q_at_core_nodes = np.array(
    ...     [ 17.02012846,  16.88791903,  13.65746194,  14.85578934,
    ...       11.41908145,  11.43630865,   8.95902559,  10.04348075,
    ...        6.28696459,   6.44316089,   4.62478522,   5.29145188])
    >>> np.allclose(mg.at_node['surface_water__discharge'][mg.core_nodes],
    ...             Q_at_core_nodes)
    True
    """
    _name = 'DischargeDiffuser'

    _input_var_names = ('topographic__elevation',
                        'water__discharge_in',
                        'sediment__discharge_in',
                        )

    _output_var_names = ('topographic__elevation',
                         'surface_water__discharge',
                         'flow__potential',
                         )

    _var_units = {'topographic__elevation': 'm',
                  'water__unit_flux_in': 'm/s',
                  'surface_water__discharge': 'm**3/s',
                  'flow__potential': 'm**3/s',
                  'surface_water__depth': 'm',
                  }

    _var_mapping = {'topographic__elevation': 'node',
                    'water__unit_flux_in': 'node',
                    'surface_water__discharge': 'node',
                    'flow__potential': 'node',
                    'surface_water__depth': 'node',
                    }

    _var_doc = {
        'topographic__elevation': 'Land surface topographic elevation',
        'water__unit_flux_in': (
            'External volume water per area per time input to each node ' +
            '(e.g., rainfall rate)'),
        'surface_water__discharge': (
            'Magnitude of volumetric water flux out of each node'),
        'flow__potential': (
            'Value of the hypothetical field "K", used to force water flux ' +
            'to flow downhill'),
        'surface_water__depth': (
            'If Manning or Chezy specified, the depth of flow in the cell, ' +
            'calculated assuming flow occurs over the whole surface'),
                  }

    _min_slope_thresh = 1.e-24
    # if your flow isn't connecting up, this probably needs to be reduced

    @use_file_name_or_kwds
    def __init__(self, grid, **kwds):
        """Initialize flow router.
        """
        if RasterModelGrid in inspect.getmro(grid.__class__):
            assert grid.number_of_node_rows >= 3
            assert grid.number_of_node_columns >= 3
            self._raster = True
        else:
            self._raster = False

        assert self._raster = True  # ...for now

        self._grid = grid

        # hacky fix because water__discharge is defined on both links and nodes
        for out_field in self._output_var_names:
            if self._var_mapping[out_field] == 'node':
                try:
                    self.grid.add_zeros(self._var_mapping[out_field],
                                        out_field, dtype=float)
                except FieldError:
                    pass
            else:
                pass
            try:
                self.grid.add_zeros('node', 'surface_water__discharge',
                                    dtype=float)
            except FieldError:
                pass
        ni = grid.number_of_node_rows
        nj = grid.number_of_node_columns

        self._K = grid.zeros('node', dtype=float)
        self._prevK = grid.zeros('node', dtype=float)
        self._znew = grid.zeros('node', dtype=float)
        # discharge across north, south, west, and east face of control volume
        self._Qn = np.zeros((ni, nj), dtype='float')
        self._Qs = np.zeros((ni, nj), dtype='float')
        self._Qw = np.zeros((ni, nj), dtype='float')
        self._Qe = np.zeros((ni, nj), dtype='float')

        # coefficenst used in solition of flow conductivity K
        self._app = np.zeros((ni, nj), dtype='float')
        self._apz = np.zeros((ni, nj), dtype='float')
        self._aww = np.zeros((ni, nj), dtype='float')
        self._awp = np.zeros((ni, nj), dtype='float')
        self._awz = np.zeros((ni, nj), dtype='float')
        self._aee = np.zeros((ni, nj), dtype='float')
        self._aep = np.zeros((ni, nj), dtype='float')
        self._aez = np.zeros((ni, nj), dtype='float')
        self._ass = np.zeros((ni, nj), dtype='float')
        self._asp = np.zeros((ni, nj), dtype='float')
        self._asz = np.zeros((ni, nj), dtype='float')
        self._ann = np.zeros((ni, nj), dtype='float')
        self._anp = np.zeros((ni, nj), dtype='float')
        self._anz = np.zeros((ni, nj), dtype='float')

        self._

    def run_one_step(self, **kwds):
        """
        """
        grid = self.grid
        ni = grid.number_of_node_rows
        nj = grid.number_of_node_columns
        z = grid.at_node['topographic__elevation']
        Qsp = grid.at_node['water__discharge_in'].reshape(
            (grid.number_of_node_rows, grid.number_of_node_columns))
        Qsource = grid.at_node['sediment__discharge_in'].reshape(
            (grid.number_of_node_rows, grid.number_of_node_columns))
        mismatch = 10000.

        slx = np.empty((n, n), dtype=float)
        sly = np.empty((n, n), dtype=float)
        offset_slopes1 = np.empty((n, n), dtype=float)
        offset_slopes2 = np.empty((n, n), dtype=float)

        # elevation at current and new time
        # Note a horizonal surface is the initial condition
        eta = z.reshape((grid.number_of_node_rows,
                         grid.number_of_node_columns))
        etan = self._znew.reshape((grid.number_of_node_rows,
                                   grid.number_of_node_columns))

        slice_e = (slice(0, ni, 1), slice(1, nj, 1))
        slice_n = (slice(1, ni, 1), slice(0, nj, 1))
        slice_w = (slice(0, ni, 1), slice(0, nj-1, 1))
        slice_s = (slice(0, ni-1, 1), slice(0, nj, 1))
        slice_ne = (slice(1, ni, 1), slice(1, nj, 1))
        slice_sw = (slice(0, ni-1, 1), slice(0, nj-1, 1))
        slice_nw = (slice(1, ni, 1), slice(0, nj-1, 1))
        slice_se = (slice(0, ni-1, 1), slice(1, nj, 1))

        # flux west
        slx[slice_e] = (eta[slice_w] - eta[slice_e])/self.grid.dx
        slx[:, 0] = 0.
        offset_slopes1[]
        sly[] = 




        # do the ortho nodes first, in isolation
        g = grid.calc_grad_at_link(z)
        if self.equation != 'default':
            g = np.sign(g) * np.sqrt(np.fabs(g))
            # ^...because both Manning and Chezy actually follow sqrt
            # slope, not slope
        # weight by face width - NO, because diags
        # g *= grid.width_of_face[grid.face_at_link]
        link_grad_at_node_w_dir = (
            g[grid.links_at_node] * grid.active_link_dirs_at_node)
        # active_link_dirs strips "wrong" face widths

        # now outgoing link grad sum
        outgoing_sum = (np.sum((link_grad_at_node_w_dir).clip(0.), axis=1) +
                        self._min_slope_thresh)
        pos_incoming_link_grads = (-link_grad_at_node_w_dir).clip(0.)

        if not self.route_on_diagonals or not self._raster:
            while mismatch > 1.e-6:
                K_link_ends = self._K[grid.neighbors_at_node]
                incoming_K_sum = (pos_incoming_link_grads*K_link_ends
                                  ).sum(axis=1) + self._min_slope_thresh
                self._K[:] = (incoming_K_sum + Qwater_in)/outgoing_sum
                mismatch = np.sum(np.square(self._K-prev_K))
                prev_K = self._K.copy()

            upwind_K = grid.map_value_at_max_node_to_link(z, self._K)
            self._discharges_at_link[:] = upwind_K * g
            self._discharges_at_link[grid.status_at_link == INACTIVE_LINK] = 0.
        else:
            # grad on diags:
            gwd = np.empty(grid._number_of_d8_links, dtype=float)
            gd = gwd[grid.number_of_links:]
            gd[:] = (z[grid._diag_link_tonode] - z[grid._diag_link_fromnode])
            gd /= (grid._length_of_link_with_diagonals[grid.number_of_links:])
            if self.equation != 'default':
                gd[:] = np.sign(gd)*np.sqrt(np.fabs(gd))
            diag_grad_at_node_w_dir = (gwd[grid._diagonal_links_at_node] *
                                       grid._diag_active_link_dirs_at_node)

            outgoing_sum += np.sum(diag_grad_at_node_w_dir.clip(0.), axis=1)
            pos_incoming_diag_grads = (-diag_grad_at_node_w_dir).clip(0.)
            while mismatch > 1.e-6:
                K_link_ends = self._K[grid.neighbors_at_node]
                K_diag_ends = self._K[grid._diagonal_neighbors_at_node]
                incoming_K_sum = ((pos_incoming_link_grads * K_link_ends
                                   ).sum(axis=1) +
                                  (pos_incoming_diag_grads * K_diag_ends
                                   ).sum(axis=1) + self._min_slope_thresh)
                self._K[:] = (incoming_K_sum + Qwater_in) / outgoing_sum
                mismatch = np.sum(np.square(self._K - prev_K))
                prev_K = self._K.copy()

            # ^this is necessary to suppress stupid apparent link Qs at flow
            # edges, if present.
            upwind_K = grid.map_value_at_max_node_to_link(z, self._K)
            upwind_diag_K = np.where(
                z[grid._diag_link_tonode] > z[grid._diag_link_fromnode],
                self._K[grid._diag_link_tonode],
                self._K[grid._diag_link_fromnode])
            self._discharges_at_link[:grid.number_of_links] = upwind_K * g
            self._discharges_at_link[grid.number_of_links:] = (
                upwind_diag_K * gd)
            self._discharges_at_link[grid._all_d8_inactive_links] = 0.

        np.multiply(self._K, outgoing_sum, out=self._Qw)
        # there is no sensible way to save discharges at links, if we route
        # on diagonals.
        # for now, let's make a property

        # now process uval and vval to give the depths, if Chezy or Manning:
        if self.equation == 'Chezy':
            # Chezy: Q = C*Area*sqrt(depth*slope)
            grid.at_node['surface_water__depth'][:] = (
                grid.at_node['flow__potential'] / self.chezy_C /
                self.equiv_circ_diam) ** (2. / 3.)
        elif self.equation == 'Manning':
            # Manning: Q = w/n*depth**(5/3)
            grid.at_node['surface_water__depth'][:] = (
                grid.at_node['flow__potential'] * self.manning_n /
                self.equiv_circ_diam) ** 0.6
        else:
            pass

    def run_one_step(self, **kwds):
        """Route surface-water flow over a landscape.

        Both convergent and divergent flow can occur.
        """
        self.route_flow(**kwds)

    @property
    def discharges_at_links(self):
        """Return the discharges at links.

        Note that if diagonal routing, this will return number_of_d8_links.
        Otherwise, it will be number_of_links.
        """
        return self._discharges_at_link
