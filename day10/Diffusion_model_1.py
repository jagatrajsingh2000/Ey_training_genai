# -*- coding: utf-8 -*-
"""
Diffusion Model Demo

This script demonstrates the basic idea behind diffusion models:
- Load one CIFAR-10 image.
- Add different levels of Gaussian noise.
- Show how forward diffusion gradually destroys image information.
- Optionally run Stable Diffusion text-to-image or image-to-image examples.

The simple diffusion visualizations run locally with PyTorch and torchvision.
The Stable Diffusion examples require the diffusers package, model download,
and preferably a CUDA GPU.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import torch
import torchvision
import torchvision.transforms as transforms


BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "diffusion_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_cifar10_image(image_index=0):
    transform = transforms.Compose([
        transforms.ToTensor(),
    ])

    dataset = torchvision.datasets.CIFAR10(
        root=BASE_DIR / "data",
        train=True,
        download=True,
        transform=transform,
    )

    image, label = dataset[image_index]
    print("Class label:", dataset.classes[label])
    return image


def add_noise(x, beta):
    noise = torch.randn_like(x)
    return torch.sqrt(1 - beta) * x + torch.sqrt(beta) * noise


def save_beta_noise_comparison(x0):
    betas = [0.01, 0.05, 0.1, 0.3, 0.6]

    plt.figure(figsize=(15, 3))

    plt.subplot(1, len(betas) + 1, 1)
    plt.imshow(x0.permute(1, 2, 0).clamp(0, 1))
    plt.title("Original")
    plt.axis("off")

    for index, beta in enumerate(betas):
        xt = add_noise(x0, torch.tensor(beta))
        plt.subplot(1, len(betas) + 1, index + 2)
        plt.imshow(xt.permute(1, 2, 0).clamp(0, 1))
        plt.title(f"beta={beta}")
        plt.axis("off")

    plt.tight_layout()
    output_path = OUTPUT_DIR / "beta_noise_comparison.png"
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()

    print(f"Saved beta noise comparison: {output_path}")


def create_linear_noise_schedule(timesteps=1000, beta_start=0.0001, beta_end=0.02):
    betas = torch.linspace(beta_start, beta_end, timesteps)
    alphas = 1.0 - betas
    alpha_cumprod = torch.cumprod(alphas, dim=0)

    print(f"Number of timesteps: {timesteps}")
    print(f"First 5 betas: {betas[:5]}")
    print(f"Last 5 betas: {betas[-5:]}")

    return alpha_cumprod


def forward_diffusion_at_t(x0, t, alpha_cumprod):
    noise = torch.randn_like(x0)
    sqrt_alpha_cumprod_t = torch.sqrt(alpha_cumprod[t - 1])
    sqrt_one_minus_alpha_cumprod_t = torch.sqrt(1.0 - alpha_cumprod[t - 1])
    return sqrt_alpha_cumprod_t * x0 + sqrt_one_minus_alpha_cumprod_t * noise


def save_timestep_diffusion_comparison(x0):
    alpha_cumprod = create_linear_noise_schedule()
    visualization_timesteps = [1, 50, 100, 200, 500, 999]

    plt.figure(figsize=(15, 4))

    plt.subplot(1, len(visualization_timesteps) + 1, 1)
    plt.imshow(x0.permute(1, 2, 0).clamp(0, 1))
    plt.title("Original")
    plt.axis("off")

    for index, timestep in enumerate(visualization_timesteps):
        xt = forward_diffusion_at_t(x0, timestep, alpha_cumprod)
        plt.subplot(1, len(visualization_timesteps) + 1, index + 2)
        plt.imshow(xt.permute(1, 2, 0).clamp(0, 1))
        plt.title(f"t={timestep}")
        plt.axis("off")

    plt.tight_layout()
    output_path = OUTPUT_DIR / "timestep_diffusion_comparison.png"
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()

    print(f"Saved timestep diffusion comparison: {output_path}")


def generate_text_to_image(prompt="English alphabet"):
    from diffusers import StableDiffusionPipeline

    if not torch.cuda.is_available():
        raise RuntimeError("Stable Diffusion example requires CUDA in this script.")

    pipe = StableDiffusionPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
    ).to("cuda")

    image = pipe(prompt).images[0]
    output_path = OUTPUT_DIR / "stable_diffusion_output.png"
    image.save(output_path)

    print(f"Saved Stable Diffusion image: {output_path}")


def generate_image_to_image(
    input_image_path=BASE_DIR / "edited.png",
    prompt="Can you increase the resolution, sharpen facial features",
):
    from diffusers import StableDiffusionImg2ImgPipeline
    from PIL import Image

    if not torch.cuda.is_available():
        raise RuntimeError("Stable Diffusion image-to-image example requires CUDA.")

    init_image = Image.open(input_image_path).convert("RGB")

    pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=torch.float16,
    ).to("cuda")

    image = pipe(prompt=prompt, image=init_image, strength=0.7).images[0]
    output_path = OUTPUT_DIR / "stable_diffusion_img2img_output.png"
    image.save(output_path)

    print(f"Saved image-to-image result: {output_path}")


def main():
    print("Mathematical models related to diffusion")
    print("Forward diffusion equation:")
    print("x(t) = sqrt(1 - beta) * x(t-1) + sqrt(beta) * epsilon")
    print()
    print("Reverse process:")
    print("Instead of directly predicting the original image, a model predicts noise.")
    print("Predicting noise is easier than predicting the full image.")
    print()

    x0 = load_cifar10_image(image_index=0)

    save_beta_noise_comparison(x0)
    save_timestep_diffusion_comparison(x0)

    print()
    print("DDPM vs DDIM:")
    print("DDPM = stochastic denoising process.")
    print("DDIM = deterministic denoising process with fewer sampling steps.")


if __name__ == "__main__":
    main()
