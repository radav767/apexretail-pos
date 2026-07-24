import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

type Branch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

type Product = {
  product_id: string;
  name: string;
  sku: string | null;
  unit: string;
};

type Balance = {
  product_id: string;
  quantity: string;
};

export default function BranchTransferPanel({
  companyId,
  onDataChanged,
}: {
  companyId: string;
  onDataChanged?: () => Promise<void> | void;
}) {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [balances, setBalances] = useState<Balance[]>([]);

  const [newBranchName, setNewBranchName] = useState("");
  const [sourceBranchId, setSourceBranchId] = useState("");
  const [destinationBranchId, setDestinationBranchId] =
    useState("");
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const availableStock = useMemo(() => {
    return Number(
      balances.find(
        (balance) => balance.product_id === productId,
      )?.quantity || 0,
    );
  }, [balances, productId]);

  async function loadData() {
    const [branchResponse, productResponse] =
      await Promise.all([
        api.get(`/inventory/branches/${companyId}`),
        api.get(`/inventory/overview/${companyId}`),
      ]);

    const loadedBranches: Branch[] = branchResponse.data;
    const loadedProducts: Product[] = productResponse.data;

    setBranches(loadedBranches);
    setProducts(loadedProducts);

    setSourceBranchId((current) => {
      return loadedBranches.some(
        (branch) => branch.id === current,
      )
        ? current
        : loadedBranches[0]?.id || "";
    });

    setProductId((current) => {
      return loadedProducts.some(
        (product) => product.product_id === current,
      )
        ? current
        : loadedProducts[0]?.product_id || "";
    });
  }

  async function loadBalances(branchId: string) {
    if (!branchId) {
      setBalances([]);
      return;
    }

    const response = await api.get(
      `/inventory/branch-overview/${companyId}`,
      {
        params: {
          branch_id: branchId,
        },
      },
    );

    setBalances(response.data);
  }

  async function createBranch() {
    const name = newBranchName.trim();

    if (!name) {
      setMessage("Enter a branch name");
      return;
    }

    const shopId = branches[0]?.shop_id;

    if (!shopId) {
      setMessage("No shop is available for this company");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await api.post("/inventory/branches", {
        company_id: companyId,
        shop_id: shopId,
        name,
      });

      setNewBranchName("");
      setMessage("Branch created successfully");

      await loadData();
      await onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to create branch",
      );
    } finally {
      setLoading(false);
    }
  }

  async function transferStock() {
    const transferQuantity = Number(quantity);

    if (!sourceBranchId || !destinationBranchId) {
      setMessage(
        "Select the source and destination branches",
      );
      return;
    }

    if (sourceBranchId === destinationBranchId) {
      setMessage(
        "Source and destination branches must be different",
      );
      return;
    }

    if (!productId) {
      setMessage("Select a product");
      return;
    }

    if (
      !Number.isFinite(transferQuantity) ||
      transferQuantity <= 0
    ) {
      setMessage(
        "Transfer quantity must be greater than zero",
      );
      return;
    }

    if (transferQuantity > availableStock) {
      setMessage(
        `Only ${availableStock} unit(s) are available`,
      );
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await api.post("/inventory/transfers", {
        company_id: companyId,
        source_branch_id: sourceBranchId,
        destination_branch_id: destinationBranchId,
        reference: reference.trim() || null,
        notes: notes.trim() || null,
        items: [
          {
            product_id: productId,
            quantity,
          },
        ],
      });

      setQuantity("");
      setReference("");
      setNotes("");
      setMessage("Stock transferred successfully");

      await loadBalances(sourceBranchId);
      await onDataChanged?.();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to transfer stock",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [companyId]);

  useEffect(() => {
    const destination = branches.find(
      (branch) => branch.id !== sourceBranchId,
    );

    if (
      destinationBranchId === sourceBranchId ||
      !branches.some(
        (branch) => branch.id === destinationBranchId,
      )
    ) {
      setDestinationBranchId(destination?.id || "");
    }

    void loadBalances(sourceBranchId);
  }, [branches, sourceBranchId]);

  return (
    <div className="branch-transfer-layout">
      <section className="inventory-form-card">
        <div className="inventory-panel-header">
          <div>
            <h2>Branches</h2>
            <p>Create and review inventory locations.</p>
          </div>
        </div>

        <label className="branch-input-label">
          New branch name
          <input
            value={newBranchName}
            placeholder="Example: Bulawayo Branch"
            onChange={(event) =>
              setNewBranchName(event.target.value)
            }
          />
        </label>

        <button
          type="button"
          className="inventory-primary-button"
          onClick={createBranch}
          disabled={loading}
        >
          Create Branch
        </button>

        <div className="branch-list">
          {branches.map((branch) => (
            <article key={branch.id}>
              <strong>{branch.name}</strong>
              <span>{branch.shop_name}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="inventory-form-card">
        <div className="inventory-panel-header">
          <div>
            <h2>Stock Transfer</h2>
            <p>Move stock between branches.</p>
          </div>
        </div>

        {branches.length < 2 ? (
          <div className="inventory-empty">
            Create at least two branches first.
          </div>
        ) : (
          <>
            <div className="inventory-form-grid">
              <label>
                Source branch
                <select
                  value={sourceBranchId}
                  onChange={(event) =>
                    setSourceBranchId(event.target.value)
                  }
                >
                  {branches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.shop_name} — {branch.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Destination branch
                <select
                  value={destinationBranchId}
                  onChange={(event) =>
                    setDestinationBranchId(
                      event.target.value,
                    )
                  }
                >
                  {branches
                    .filter(
                      (branch) =>
                        branch.id !== sourceBranchId,
                    )
                    .map((branch) => (
                      <option
                        key={branch.id}
                        value={branch.id}
                      >
                        {branch.shop_name} — {branch.name}
                      </option>
                    ))}
                </select>
              </label>

              <label>
                Product
                <select
                  value={productId}
                  onChange={(event) =>
                    setProductId(event.target.value)
                  }
                >
                  {products.map((product) => (
                    <option
                      key={product.product_id}
                      value={product.product_id}
                    >
                      {product.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Quantity
                <input
                  type="number"
                  min="0.001"
                  step="0.001"
                  value={quantity}
                  onChange={(event) =>
                    setQuantity(event.target.value)
                  }
                />
                <small>
                  Source stock: {availableStock}
                </small>
              </label>

              <label>
                Reference
                <input
                  value={reference}
                  placeholder="Generated when blank"
                  onChange={(event) =>
                    setReference(event.target.value)
                  }
                />
              </label>

              <label>
                Notes
                <input
                  value={notes}
                  placeholder="Optional"
                  onChange={(event) =>
                    setNotes(event.target.value)
                  }
                />
              </label>
            </div>

            <button
              type="button"
              className="inventory-primary-button"
              onClick={transferStock}
              disabled={loading}
            >
              {loading
                ? "Processing..."
                : "Transfer Stock"}
            </button>
          </>
        )}
      </section>

      <p className="inventory-message branch-transfer-message">
        {message}
      </p>
    </div>
  );
}
