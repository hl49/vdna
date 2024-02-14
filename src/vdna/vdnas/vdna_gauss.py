from pathlib import Path
from typing import Dict, Union

import numpy as np
import torch

from ..networks import FeatureExtractionModel
from .vdna_base import VDNA


def _get_gaussian_params(features: torch.Tensor) -> Dict[str, torch.Tensor]:
    features = features.view(features.shape[0], -1)
    mu = torch.mean(features, dim=0)
    if len(features) > 1:
        var = torch.var(features, dim=0, correction=1)
    else:
        print("Warning: only one sample, variance of VDNA with Gaussian is set to 0")
        var = torch.zeros_like(mu)
    return {"mu": mu, "var": var}


class VDNAGauss(VDNA):
    def __init__(self):
        super().__init__()
        self.type = "gaussian"
        self.name = "gaussian"
        self.data = {}

    def _set_extraction_settings(self, feat_extractor: FeatureExtractionModel) -> FeatureExtractionModel:
        feat_extractor.extraction_settings.average_feats_spatially = True
        return feat_extractor

    def fit_distribution(self, features_dict: Dict[str, torch.Tensor]):
        self.data = {}
        for layer in features_dict:
            self.data[layer] = _get_gaussian_params(features_dict[layer])

    def _get_vdna_metadata(self) -> dict:
        return {}

    def _save_dist_data(self, file_path: Union[str, Path]):
        file_path = Path(file_path).with_suffix(".npz")
        data = {}
        for layer in self.data:
            data[layer] = {}
            data["mu-" + layer] = self.data[layer]["mu"].cpu().numpy().astype(np.float32)
            data["var-" + layer] = self.data[layer]["var"].cpu().numpy().astype(np.float32)
        np.savez_compressed(file_path, **data)

    def _load_dist_data(self, dist_metadata: Dict, file_path: Union[str, Path], device: str):
        file_path = Path(file_path).with_suffix(".npz")
        loaded_data = np.load(file_path)
        self.data = {}
        for layer in self.neurons_list:
            self.data[layer] = {}
            self.data[layer]["mu"] = torch.from_numpy(loaded_data["mu-" + layer]).to(device)
            self.data[layer]["var"] = torch.from_numpy(loaded_data["var-" + layer]).to(device)

    def get_neuron_dist(self, layer_name: str, neuron_idx: int) -> Dict[str, torch.Tensor]:
        return {
            "mu": self.data[layer_name]["mu"][neuron_idx],
            "var": self.data[layer_name]["var"][neuron_idx],
        }

    def get_all_neurons_in_layer_dist(self, layer_name: str) -> Dict[str, torch.Tensor]:
        mu = self.data[layer_name]["mu"]
        var = self.data[layer_name]["var"]
        return {"mu": mu, "var": var}

    def get_all_neurons_dists(self) -> Dict[str, torch.Tensor]:
        mus = []
        variances = []
        for layer_name in self.data:
            mus.append(self.data[layer_name]["mu"])
            variances.append(self.data[layer_name]["var"])
        return {"mu": torch.cat(mus), "var": torch.cat(variances)}

    def __add__(self, other):
        new_vdna = VDNAGauss()
        new_vdna = self._common_before_add(other, new_vdna)

        for layer in self.data:
            new_vdna.data[layer] = {}
            new_vdna.data[layer]["mu"] = (
                self.data[layer]["mu"] * self.num_images + other.data[layer]["mu"] * other.num_images
            ) / (self.num_images + other.num_images)

            new_vdna.data[layer]["var"] = (
                self.data[layer]["var"] * (self.num_images - 1)
                + self.num_images * (self.data[layer]["mu"] - new_vdna.data[layer]["mu"]) ** 2
                + other.data[layer]["var"] * (other.num_images - 1)
                + other.num_images * (other.data[layer]["mu"] - new_vdna.data[layer]["mu"]) ** 2
            ) / (self.num_images + other.num_images - 1)
        return new_vdna
