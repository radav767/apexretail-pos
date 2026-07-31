import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "./api/client";
import PosModulePage, { type PosModuleName } from "./PosModulePage";
import { registerCurrentDevice } from "./device";

type Product = {
  id: string;
  name: string;
  sku?: string;
  barcode?: string;
  selling_price: string;
  stock_qty: string;
};

type CartItem = Product & {
  qty: number;
};

type Receipt = {
  id: string;
  receipt_number: string;
  subtotal_amount?: string;
  tax_name?: string | null;
  tax_rate?: string;
  tax_amount?: string;
  tax_inclusive?: boolean;
  total_amount: string;
  amount_received: string;
  change_due: string;
  payment_method: string;
  status: string;
};


type BusinessSettings = {
  currency_code?: string;
  currency_symbol?: string;
  decimal_places?: number;
  tax_name?: string;
  tax_rate?: string;
  tax_inclusive?: boolean;
  receipt_header?: string | null;
  receipt_footer?: string | null;
  paper_size?: string;
  auto_print?: boolean;
  payment_methods?: string[];
};

type CashierSession = {
  id: string;
  name: string;
  role: string;
  branch_id: string;
  permissions?: Record<string, boolean>;
};


function App() {
  const [email, setEmail] = useState("owner001@example.com");
  const [password, setPassword] = useState("12345678");
  const [companyId, setCompanyId] = useState(
    localStorage.getItem("company_id") || "",
  );
  
  const [branchId, setBranchId] = useState(
    localStorage.getItem("branch_id") || "",
  );

const [loggedIn, setLoggedIn] = useState(
    Boolean(localStorage.getItem("token")),
  );

  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [search, setSearch] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [message, setMessage] = useState("");
  const [processing, setProcessing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activePosModule, setActivePosModule] = useState<PosModuleName>("Sales");

  const [showTender, setShowTender] = useState(false);
  const [amountReceived, setAmountReceived] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [receiptItems, setReceiptItems] = useState<CartItem[]>([]);
  const [businessSettings, setBusinessSettings] =
    useState<BusinessSettings | null>(null);

  const [cashier, setCashier] =
    useState<CashierSession | null>(null);
  const [cashierPin, setCashierPin] = useState("");
  const [pinLoading, setPinLoading] = useState(false);
  const [pinMessage, setPinMessage] = useState("");

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return products.filter((product) =>
      product.name.toLowerCase().includes(query) ||
      (product.sku || "").toLowerCase().includes(query) ||
      (product.barcode || "").toLowerCase().includes(query)
    );
  }, [products, search]);

  const roundSaleAmount = (value: number) =>
    Math.round((value + Number.EPSILON) * 100) / 100;

  const cartAmount = roundSaleAmount(
    cart.reduce(
      (sum, item) =>
        sum + Number(item.selling_price) * item.qty,
      0,
    ),
  );

  const configuredTaxRate = Math.max(
    0,
    Number(businessSettings?.tax_rate || 0),
  );

  const taxInclusive = Boolean(
    businessSettings?.tax_inclusive,
  );

  const taxName =
    businessSettings?.tax_name?.trim() || "Tax";

  let subtotal = cartAmount;
  let taxAmount = 0;
  let total = cartAmount;

  if (configuredTaxRate > 0) {
    if (taxInclusive) {
      total = cartAmount;

      taxAmount = roundSaleAmount(
        total *
          (configuredTaxRate /
            (100 + configuredTaxRate)),
      );

      subtotal = roundSaleAmount(
        total - taxAmount,
      );
    } else {
      subtotal = cartAmount;

      taxAmount = roundSaleAmount(
        subtotal *
          (configuredTaxRate / 100),
      );

      total = roundSaleAmount(
        subtotal + taxAmount,
      );
    }
  }

  const numericAmountReceived = Number(amountReceived || 0);
  const previewChange = Math.max(0, numericAmountReceived - total);

  async function loadBusinessSettings(
    selectedCompanyId: string,
  ) {
    if (!selectedCompanyId) {
      return;
    }

    const response = await api.get(
      `/settings/${selectedCompanyId}`,
    );

    const loadedSettings =
      response.data as BusinessSettings;

    setBusinessSettings(loadedSettings);

    const methods = (
      loadedSettings.payment_methods || []
    )
      .map((method) =>
        String(method).trim().toLowerCase(),
      )
      .filter(Boolean);

    if (methods.length) {
      setPaymentMethod((currentMethod) =>
        methods.includes(currentMethod)
          ? currentMethod
          : methods[0],
      );
    }
  }

  const currencySymbol =
    businessSettings?.currency_symbol || "$";

  const decimalPlaces =
    businessSettings?.decimal_places ?? 2;

  function formatMoney(value: number | string) {
    const numericValue = Number(value || 0);

    return `${currencySymbol}${numericValue.toFixed(
      decimalPlaces,
    )}`;
  }

  const enabledPaymentMethods = useMemo(() => {
    const methods = (
      businessSettings?.payment_methods || []
    )
      .map((method) =>
        String(method).trim().toLowerCase(),
      )
      .filter(Boolean);

    return methods.length
      ? methods
      : ["cash", "card", "mobile", "credit"];
  }, [businessSettings]);

  async function loadProducts(
    id = companyId,
    selectedBranchId = branchId,
  ) {
    if (!id) return;

    try {
      const productResponse = await api.get(
        `/products/${id}`,
      );

      let loadedProducts = productResponse.data;

      if (selectedBranchId) {
        const balanceResponse = await api.get(
          `/inventory/branch-overview/${id}`,
          {
            params: {
              branch_id: selectedBranchId,
            },
          },
        );

        const balances = new Map<string, string>(
          balanceResponse.data.map((balance: any) => [
            balance.product_id,
            balance.quantity,
          ]),
        );

        loadedProducts = loadedProducts.map(
          (product: Product) => ({
            ...product,
            stock_qty:
              balances.get(product.id) || "0",
          }),
        );
      }

      setProducts(loadedProducts);
    } catch (error) {
      console.error(error);
      setMessage("Failed to load branch products");
    }
  }

  async function login() {
    try {
      setMessage("");

      const response = await api.post("/auth/login", {
        email,
        password,
      });

      localStorage.setItem("token", response.data.token);
      localStorage.setItem("company_id", response.data.company_id);

      setCompanyId(response.data.company_id);
      setLoggedIn(true);

      await loadProducts(response.data.company_id);
      await loadBusinessSettings(response.data.company_id);
    } catch (error: any) {
      setMessage(error.response?.data?.detail || "Login failed");
    }
  }

  async function loginWithEmployeePin() {
    if (!companyId) {
      setPinMessage("Business session is not available");
      return;
    }

    if (!branchId) {
      setPinMessage("This POS device is not assigned to a branch");
      return;
    }

    if (!/^\d{4}$/.test(cashierPin)) {
      setPinMessage("Enter your four-digit employee PIN");
      return;
    }

    try {
      setPinLoading(true);
      setPinMessage("");

      const response = await api.post(
        "/employees/pin-login",
        {
          company_id: companyId,
          branch_id: branchId,
          pin: cashierPin,
        },
      );

      const result =
        response.data?.employee || response.data;

      const employeeId =
        result?.id || result?.employee_id || "";

      if (!employeeId) {
        throw new Error(
          "Employee login response has no employee ID",
        );
      }

      if (result.permissions?.sales === false) {
        setPinMessage(
          "This employee does not have permission to make sales",
        );
        return;
      }

      setCashier({
        id: employeeId,
        name: result.name || "Employee",
        role: result.role || "cashier",
        branch_id: result.branch_id || branchId,
        permissions: result.permissions || {},
      });

      setCashierPin("");
      setMessage("");
    } catch (error: any) {
      setCashierPin("");

      setPinMessage(
        error.response?.data?.detail ||
          error.message ||
          "Invalid employee PIN",
      );
    } finally {
      setPinLoading(false);
    }
  }

  function switchCashier() {
    setCashier(null);
    setCashierPin("");
    setPinMessage("");
    setCart([]);
    setShowTender(false);
    setAmountReceived("");
    setReceipt(null);
    setReceiptItems([]);
    setMessage("");
  }



  function addToCart(product: Product) {
    const availableStock = Number(product.stock_qty);

    if (availableStock <= 0) {
      setMessage(`${product.name} is out of stock`);
      return;
    }

    setCart((currentCart) => {
      const existing = currentCart.find(
        (item) => item.id === product.id,
      );

      if (existing) {
        if (existing.qty >= availableStock) {
          setMessage(`Only ${availableStock} available`);
          return currentCart;
        }

        return currentCart.map((item) =>
          item.id === product.id
            ? { ...item, qty: item.qty + 1 }
            : item
        );
      }

      return [...currentCart, { ...product, qty: 1 }];
    });
  }

  function changeQty(id: string, difference: number) {
    setCart((currentCart) =>
      currentCart.map((item) => {
        if (item.id !== id) return item;

        const availableStock = Number(item.stock_qty);
        const nextQty = item.qty + difference;

        return {
          ...item,
          qty: Math.min(availableStock, Math.max(1, nextQty)),
        };
      })
    );
  }

  function removeFromCart(id: string) {
    setCart((currentCart) =>
      currentCart.filter((item) => item.id !== id)
    );
  }

  function startPayment() {
    setMessage("");

    if (!cart.length) {
      setMessage("Add at least one product to the cart");
      return;
    }

    if (paymentMethod === "cash") {
      setAmountReceived(total.toFixed(2));
      setShowTender(true);
      return;
    }

    void submitSale();
  }

  async function submitSale(cashAmount?: number) {
    if (!cart.length || processing) return;

    if (!cashier) {
      setMessage("Cashier PIN is required");
      return;
    }

    try {
      setProcessing(true);
      setMessage("");

      const payload: {
        company_id: string;
      branch_id?: string | null;
      employee_id: string;
        payment_method: string;
        amount_received?: string;
        items: Array<{
          product_id: string;
          quantity: number;
        }>;
      } = {
        company_id: companyId,
      branch_id: branchId || null,
      employee_id: cashier.id,
        payment_method: paymentMethod,
        items: cart.map((item) => ({
          product_id: item.id,
          quantity: item.qty,
        })),
      };

      if (paymentMethod === "cash") {
        const received = cashAmount ?? numericAmountReceived;

        if (!Number.isFinite(received) || received < total) {
          setMessage("Amount received is less than the total");
          return;
        }

        payload.amount_received = received.toFixed(2);
      }

      const completedItems = [...cart];
      const response = await api.post("/sales", payload);

      setReceipt(response.data);
      setReceiptItems(completedItems);
      setShowTender(false);
      setCart([]);
      setAmountReceived("");
      setMessage("Sale completed successfully");

      await loadProducts(companyId, branchId);
    } catch (error: any) {
      setMessage(error.response?.data?.detail || "Sale failed");
    } finally {
      setProcessing(false);
    }
  }

  function printReceipt() {
    if (!receipt) return;

    const receiptWindow = window.open(
      "",
      "_blank",
      "width=420,height=700",
    );

    if (!receiptWindow) {
      setMessage("Please allow pop-ups to print the receipt");
      return;
    }

    const itemRows = receiptItems
      .map(
        (item) => `
          <tr>
            <td>${escapeHtml(item.name)}</td>
            <td style="text-align:center">${item.qty}</td>
            <td style="text-align:right">
              $${(Number(item.selling_price) * item.qty).toFixed(2)}
            </td>
          </tr>
        `,
      )
      .join("");

    receiptWindow.document.write(`
      <!doctype html>
      <html>
        <head>
          <title>${escapeHtml(receipt.receipt_number)}</title>
          <style>
            body {
              width: 300px;
              margin: 20px auto;
              font-family: Arial, sans-serif;
              color: #111;
            }
            h2, p {
              text-align: center;
              margin: 5px 0;
            }
            table {
              width: 100%;
              border-collapse: collapse;
              margin-top: 18px;
            }
            th, td {
              padding: 7px 2px;
              border-bottom: 1px dashed #999;
              font-size: 13px;
            }
            .summary {
              margin-top: 18px;
              font-size: 14px;
            }
            .summary div {
              display: flex;
              justify-content: space-between;
              padding: 4px 0;
            }
            .total {
              font-size: 18px;
              font-weight: bold;
            }
            @media print {
              body {
                margin: 0 auto;
              }
            }
          </style>
        </head>
        <body>
          <h2>ApexRetail POS</h2>
          <p>Receipt: ${escapeHtml(receipt.receipt_number)}</p>
          <p>${new Date().toLocaleString()}</p>

          <table>
            <thead>
              <tr>
                <th style="text-align:left">Item</th>
                <th>Qty</th>
                <th style="text-align:right">Total</th>
              </tr>
            </thead>
            <tbody>${itemRows}</tbody>
          </table>

          <div class="summary">
            <div class="total">
              <span>Total</span>
              <span>$${Number(receipt.total_amount).toFixed(2)}</span>
            </div>
            <div>
              <span>Payment</span>
              <span>${escapeHtml(receipt.payment_method.toUpperCase())}</span>
            </div>
            <div>
              <span>Received</span>
              <span>$${Number(receipt.amount_received).toFixed(2)}</span>
            </div>
            <div>
              <span>Change</span>
              <span>$${Number(receipt.change_due).toFixed(2)}</span>
            </div>
          </div>

          <p style="margin-top:24px">Thank you for shopping with us.</p>
        </body>
      </html>
    `);

    receiptWindow.document.close();
    receiptWindow.focus();
    receiptWindow.print();
  }

  function newSale() {
    setReceipt(null);
    setReceiptItems([]);
    setPaymentMethod("cash");
    setMessage("");
    setSearch("");
  }

  function showPosModule(
    moduleName: PosModuleName,
  ) {
    setActivePosModule(moduleName);
    setMenuOpen(false);
    setMessage("");
  }

  function openBackoffice() {
    setMenuOpen(false);

    window.open(
      "https://backoffice.apexpos.cloud",
      "_blank",
      "noopener,noreferrer",
    );
  }

  function logout() {
    const savedDeviceKey =
      localStorage.getItem("device_key");

    localStorage.clear();

    if (savedDeviceKey) {
      localStorage.setItem(
        "device_key",
        savedDeviceKey,
      );
    }

    setBranchId("");
    setCashier(null);
    setCashierPin("");
    setPinMessage("");
    setLoggedIn(false);
    setProducts([]);
    setCart([]);
    setReceipt(null);
    setReceiptItems([]);
    setCompanyId("");
  }

  useEffect(() => {
    if (!loggedIn || !companyId) {
      return;
    }

    let cancelled = false;

    async function synchronizeDevice() {
      try {
        const device = await registerCurrentDevice(
          companyId,
        );

        if (cancelled) {
          return;
        }

        const assignedBranchId =
          device.branch_id || "";

        setBranchId(assignedBranchId);

        await loadProducts(
          companyId,
          assignedBranchId,
        );
        await loadBusinessSettings(companyId);
      } catch (error: any) {
        console.error(
          "POS device synchronization failed:",
          error,
        );

        if (!cancelled) {
          setMessage(
            error.response?.data?.detail ||
              "POS device synchronization failed",
          );
        }
      }
    }

    void synchronizeDevice();

    return () => {
      cancelled = true;
    };
  }, [loggedIn, companyId]);

  if (!loggedIn) {
    return (
      <div style={pageCenter}>
        <div style={loginCard}>
          <button

            type="button"

            aria-label="Open POS menu"

            aria-expanded={menuOpen}

            style={posMenuTrigger}

            onClick={() => setMenuOpen((current) => !current)}

          >

            ☰

          </button>


          {menuOpen && (

            <>

              <button

                type="button"

                aria-label="Close POS menu"

                style={posMenuOverlay}

                onClick={() => setMenuOpen(false)}

              />


              <aside style={posMenuPanel}>

                <div style={posMenuHeader}>

                  <strong style={posMenuBrand}>ApexRetail POS</strong>

                  <span style={posMenuSubtitle}>Point of Sale Menu</span>

                </div>


                <div style={posMenuSession}>

                  <strong>{cashier?.name || "Cashier"}</strong>

                  <span>{cashier?.role || "employee"}</span>

                </div>


                <nav style={posMenuNavigation}>

                  <button

                    type="button"

                    style={{ ...posMenuButton, ...posMenuActiveButton }}

                    onClick={() => showPosModule("Sales")}

                  >

                    Sales

                  </button>


                  <button

                    type="button"

                    style={posMenuButton}

                    onClick={() => showPosModule("Sales Management")}

                  >

                    Sales Management

                  </button>


                  <button

                    type="button"

                    style={posMenuButton}

                    onClick={() => showPosModule("Products")}

                  >

                    Products

                  </button>


                  <button

                    type="button"

                    style={posMenuButton}

                    onClick={() => showPosModule("Inventory")}

                  >

                    Inventory

                  </button>


                  <button

                    type="button"

                    style={posMenuButton}

                    onClick={() => showPosModule("Reports")}

                  >

                    Reports

                  </button>


                  <button

                    type="button"

                    style={posMenuButton}

                    onClick={() => showPosModule("Settings")}

                  >

                    Settings

                  </button>


                  <button

                    type="button"

                    style={{ ...posMenuButton, ...posMenuBackofficeButton }}

                    onClick={openBackoffice}

                  >

                    Backoffice

                  </button>

                </nav>


                <button

                  type="button"

                  style={posMenuLogoutButton}

                  onClick={() => {

                    setMenuOpen(false);

                    logout();

                  }}

                >

                  Log out

                </button>

              </aside>

            </>

          )}


          <div style={{ paddingLeft: 58 }}>

            <h1 style={brand}>ApexRetail POS</h1>

          </div>
          <p style={{ textAlign: "center" }}>
            Sign in to your shop
          </p>

          <input
            style={input}
            value={email}
            placeholder="Email"
            onChange={(event) => setEmail(event.target.value)}
          />

          <input
            style={input}
            type="password"
            value={password}
            placeholder="Password"
            onChange={(event) => setPassword(event.target.value)}
          />

          <button style={primaryButton} onClick={login}>
            Login
          </button>

          <p style={errorText}>{message}</p>
        </div>
      </div>
    );
  }


  if (loggedIn && !branchId) {
    return (
      <div style={pageCenter}>
        <div style={loginCard}>
          <h1 style={brand}>Preparing POS</h1>

          <p style={{ textAlign: "center" }}>
            Synchronizing this device with its assigned branch.
          </p>

          {message && (
            <p style={{ textAlign: "center", color: "#b42318" }}>
              {message}
            </p>
          )}

          <button
            type="button"
            style={secondaryButton}
            onClick={logout}
          >
            Full Logout
          </button>
        </div>
      </div>
    );
  }

  if (loggedIn && !cashier) {
    return (
      <div style={pageCenter}>
        <div style={loginCard}>
          <h1 style={brand}>Cashier Sign In</h1>

          <p style={{ textAlign: "center" }}>
            Enter your four-digit employee PIN
          </p>

          <p
            style={{
              textAlign: "center",
              margin: "6px 0 18px",
              color: "#667085",
            }}
          >
            {localStorage.getItem("branch_name") ||
              "Assigned branch"}
          </p>

          <input
            style={{
              ...input,
              textAlign: "center",
              fontSize: 28,
              letterSpacing: 12,
            }}
            type="password"
            inputMode="numeric"
            autoFocus
            maxLength={4}
            value={cashierPin}
            placeholder="••••"
            onChange={(event) =>
              setCashierPin(
                event.target.value
                  .replace(/\D/g, "")
                  .slice(0, 4),
              )
            }
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void loginWithEmployeePin();
              }
            }}
          />

          <button
            type="button"
            style={primaryButton}
            disabled={pinLoading}
            onClick={() => void loginWithEmployeePin()}
          >
            {pinLoading ? "Signing in..." : "Open POS"}
          </button>

          {pinMessage && (
            <p
              style={{
                textAlign: "center",
                color: "#b42318",
                fontWeight: 700,
              }}
            >
              {pinMessage}
            </p>
          )}

          <button
            type="button"
            style={secondaryButton}
            onClick={logout}
          >
            Use Email Login
          </button>
        </div>
      </div>
    );
  }


  return (
    <div style={appShell}>
      <button

                  type="button"

                  aria-label="Open POS menu"

                  aria-expanded={menuOpen}

                  style={posMenuTrigger}

                  onClick={() => setMenuOpen((current) => !current)}

                >

                  ☰

                </button>


                {menuOpen && (

                  <>

                    <button

                      type="button"

                      aria-label="Close POS menu"

                      style={posMenuOverlay}

                      onClick={() => setMenuOpen(false)}

                    />


                    <aside style={posMenuPanel}>

                      <div style={posMenuHeader}>

                        <strong style={posMenuBrand}>ApexRetail POS</strong>

                        <span style={posMenuSubtitle}>Point of Sale Menu</span>

                      </div>


                      <div style={posMenuSession}>

                        <strong>{cashier?.name || "Cashier"}</strong>

                        <span>{cashier?.role || "employee"}</span>

                      </div>


                      <nav style={posMenuNavigation}>

                        <button

                          type="button"

                          style={{ ...posMenuButton, ...posMenuActiveButton }}

                          onClick={() => showPosModule("Sales")}

                        >

                          Sales

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Sales Management")}

                        >

                          Sales Management

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Products")}

                        >

                          Products

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Inventory")}

                        >

                          Inventory

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Reports")}

                        >

                          Reports

                        </button>


                        <button

                          type="button"

                          style={posMenuButton}

                          onClick={() => showPosModule("Settings")}

                        >

                          Settings

                        </button>


                        <button

                          type="button"

                          style={{ ...posMenuButton, ...posMenuBackofficeButton }}

                          onClick={openBackoffice}

                        >

                          Backoffice

                        </button>

                      </nav>


                      <button

                        type="button"

                        style={posMenuLogoutButton}

                        onClick={() => {

                          setMenuOpen(false);

                          logout();

                        }}

                      >

                        Log out

                      </button>

                    </aside>

                  </>

                )}

      {activePosModule !== "Sales" && (
        <PosModulePage
          activeModule={activePosModule}
          companyId={companyId}
          branchId={branchId}
          currencySymbol={currencySymbol}
          decimalPlaces={decimalPlaces}
          onBackToSales={() => {
            setActivePosModule("Sales");
            setMessage("");
          }}
        />
      )}

      <main style={mainArea}>
        <div style={topBar}>
          <div>
            <h1 style={{ margin: 0, fontSize: 32 }}>
              ApexRetail POS
            </h1>
            <p style={{ margin: "4px 0 0" }}>
            Sales screen
          </p>
          <p
            style={{
              margin: "5px 0 0",
              color: "#667085",
              fontSize: 14,
            }}
          >
            Cashier: <strong>{cashier?.name || "Employee"}</strong>
            {" · "}
            {localStorage.getItem("branch_name") ||
              "Assigned branch"}
          </p>
          </div>

          <button
          type="button"
          onClick={switchCashier}
          style={{
            ...secondaryButton,
            width: 150,
            marginTop: 0,
          }}
        >
          Switch Cashier
        </button>

        <button
            onClick={logout}
            style={{
              ...secondaryButton,
              width: 120,
              marginTop: 0,
            }}
          >
            Logout
          </button>
        </div>

        <input
          style={searchBox}
          placeholder="Search product by name, SKU or barcode..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        <div style={productGrid}>
          {filteredProducts.map((product) => (
            <button
              key={product.id}
              onClick={() => addToCart(product)}
              style={productCard}
              disabled={Number(product.stock_qty) <= 0}
            >
              <h3>{product.name}</h3>
              <p>SKU: {product.sku || "-"}</p>
              <p>Stock: {product.stock_qty}</p>
              <h2>{formatMoney(product.selling_price)}</h2>
            </button>
          ))}
        </div>

        {!filteredProducts.length && (
          <p>No matching products found.</p>
        )}
      </main>

      <aside style={cartPanel}>
        <h2 style={{ marginTop: 0 }}>Current Sale</h2>

        <div style={cartItemsArea}>
          {!cart.length && (
            <p style={{ color: "#6b7280" }}>
              Select a product to begin.
            </p>
          )}

          {cart.map((item) => (
            <div key={item.id} style={cartRow}>
              <div>
                <strong>{item.name}</strong>
                <p style={{ margin: "5px 0 0" }}>
                  {formatMoney(item.selling_price)}
                </p>
              </div>

              <div style={quantityBox}>
                <button
                  style={quantityButton}
                  onClick={() => changeQty(item.id, -1)}
                >
                  −
                </button>

                <strong>{item.qty}</strong>

                <button
                  style={quantityButton}
                  onClick={() => changeQty(item.id, 1)}
                >
                  +
                </button>
              </div>

              <button
                style={removeButton}
                onClick={() => removeFromCart(item.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div data-tax-summary="true"
          style={{
            marginTop: 22,
            marginBottom: 20,
            display: "grid",
            gap: 9,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 18,
            }}
          >
            <span>Subtotal</span>
            <strong>{formatMoney(subtotal)}</strong>
          </div>

          {configuredTaxRate > 0 && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 18,
              }}
            >
              <span>
                {taxName} ({configuredTaxRate}%)
                {taxInclusive ? " included" : ""}
              </span>
              <strong>{formatMoney(taxAmount)}</strong>
            </div>
          )}

          <h1
            style={{
              fontSize: 42,
              margin: "10px 0 0",
              display: "flex",
              justifyContent: "space-between",
            }}
          >
            <span>Total:</span>
            <span>{formatMoney(total)}</span>
          </h1>
        </div>

        <div style={paymentGrid}>
          {enabledPaymentMethods.map((method) => (
            <button
              key={method}
              onClick={() => setPaymentMethod(method)}
              style={
                paymentMethod === method
                  ? activePaymentButton
                  : secondaryButton
              }
            >
              {method.toUpperCase()}
            </button>
          ))}
        </div>

        <button
          style={primaryButton}
          onClick={startPayment}
          disabled={processing || !cart.length}
        >
          {processing ? "Processing..." : "Complete Sale"}
        </button>

        <button
          style={secondaryButton}
          onClick={() => setCart([])}
          disabled={!cart.length}
        >
          Clear Cart
        </button>

        <p style={messageText}>{message}</p>
      </aside>

      {showTender && (
        <div style={overlay}>
          <div style={modalCard}>
            <h2 style={{ marginTop: 0 }}>Cash Tender</h2>

            <p style={modalLabel}>Amount due</p>
            <h1 style={modalTotal}>${total.toFixed(2)}</h1>

            <label style={modalLabel}>Amount received</label>
            <input
              autoFocus
              type="number"
              min={total}
              step="0.01"
              value={amountReceived}
              style={tenderInput}
              onChange={(event) =>
                setAmountReceived(event.target.value)
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void submitSale(numericAmountReceived);
                }
              }}
            />

            <div style={quickAmountGrid}>
              <button
                style={secondaryButton}
                onClick={() => setAmountReceived(total.toFixed(2))}
              >
                Exact
              </button>

              {[5, 10, 20].map((increment) => (
                <button
                  key={increment}
                  style={secondaryButton}
                  onClick={() =>
                    setAmountReceived(
                      (Math.ceil(total / increment) * increment).toFixed(2),
                    )
                  }
                >
                  Next ${increment}
                </button>
              ))}
            </div>

            <div style={changeBox}>
              <span>Change due</span>
              <strong>${previewChange.toFixed(2)}</strong>
            </div>

            <button
              style={primaryButton}
              disabled={
                processing ||
                !Number.isFinite(numericAmountReceived) ||
                numericAmountReceived < total
              }
              onClick={() =>
                void submitSale(numericAmountReceived)
              }
            >
              {processing ? "Processing..." : "Confirm Payment"}
            </button>

            <button
              style={secondaryButton}
              onClick={() => {
                setShowTender(false);
                setAmountReceived("");
              }}
            >
              Cancel
            </button>

            <p style={errorText}>{message}</p>
          </div>
        </div>
      )}

      {receipt && (
        <div style={overlay}>
          <div style={modalCard}>
            <div style={successMark}>✓</div>
            <h2 style={{ textAlign: "center" }}>
              Sale Completed
            </h2>

            <p style={{ textAlign: "center" }}>
              Receipt {receipt.receipt_number}
            </p>

            <div style={receiptSummary}>
              <div>
                <span>Total</span>
                <strong>
                  ${Number(receipt.total_amount).toFixed(2)}
                </strong>
              </div>

              <div>
                <span>Amount received</span>
                <strong>
                  ${Number(receipt.amount_received).toFixed(2)}
                </strong>
              </div>

              <div>
                <span>Change due</span>
                <strong>
                  ${Number(receipt.change_due).toFixed(2)}
                </strong>
              </div>

              <div>
                <span>Payment method</span>
                <strong>
                  {receipt.payment_method.toUpperCase()}
                </strong>
              </div>
            </div>

            <button style={primaryButton} onClick={printReceipt}>
              Print Receipt
            </button>

            <button style={secondaryButton} onClick={newSale}>
              New Sale
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };

    return entities[character];
  });
}

const pageCenter: CSSProperties = {
  minHeight: "100vh",
  display: "grid",
  placeItems: "center",
  background: "#eef2f7",
};

const loginCard: CSSProperties = {
  width: 400,
  maxWidth: "calc(100vw - 32px)",
  background: "white",
  padding: 34,
  borderRadius: 22,
  boxShadow: "0 12px 35px #0002",
};

const brand: CSSProperties = {
  textAlign: "center",
  fontSize: 34,
  fontWeight: 900,
};

const input: CSSProperties = {
  width: "100%",
  padding: 14,
  marginTop: 14,
  borderRadius: 10,
  border: "1px solid #d1d5db",
};

const appShell: CSSProperties = {
  minHeight: "100vh",
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 420px",
  background: "#eef2f7",
};

const mainArea: CSSProperties = {
  minWidth: 0,
  padding: 28,
};

const topBar: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 20,
  marginBottom: 20,
};

const searchBox: CSSProperties = {
  width: "100%",
  padding: 16,
  borderRadius: 14,
  border: "1px solid #d1d5db",
  marginBottom: 22,
};

const productGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns:
    "repeat(auto-fill, minmax(190px, 1fr))",
  gap: 18,
};

const productCard: CSSProperties = {
  background: "white",
  border: 0,
  borderRadius: 18,
  padding: 24,
  textAlign: "left",
  boxShadow: "0 8px 22px #0001",
  cursor: "pointer",
};

const cartPanel: CSSProperties = {
  background: "white",
  padding: 26,
  boxShadow: "-6px 0 24px #0001",
  display: "flex",
  flexDirection: "column",
};

const cartItemsArea: CSSProperties = {
  flex: 1,
  minHeight: 250,
  maxHeight: "50vh",
  overflowY: "auto",
};

const cartRow: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) 105px 34px",
  gap: 8,
  alignItems: "center",
  borderBottom: "1px solid #eee",
  padding: "12px 0",
};

const quantityBox: CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "center",
  justifyContent: "center",
};

const quantityButton: CSSProperties = {
  width: 30,
  height: 30,
  border: 0,
  borderRadius: 7,
  background: "#e5e7eb",
  fontWeight: 800,
};

const removeButton: CSSProperties = {
  width: 30,
  height: 30,
  border: 0,
  borderRadius: 7,
  background: "#fee2e2",
  color: "#b91c1c",
  fontWeight: 900,
};

const paymentGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 10,
};

const primaryButton: CSSProperties = {
  width: "100%",
  padding: 15,
  marginTop: 16,
  background: "#111827",
  color: "white",
  border: 0,
  borderRadius: 12,
  fontWeight: 800,
};

const secondaryButton: CSSProperties = {
  width: "100%",
  padding: 13,
  marginTop: 10,
  background: "#e5e7eb",
  color: "#111827",
  border: 0,
  borderRadius: 12,
  fontWeight: 700,
};

const activePaymentButton: CSSProperties = {
  ...secondaryButton,
  background: "#111827",
  color: "white",
};

const overlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 1000,
  background: "rgba(15, 23, 42, 0.62)",
  display: "grid",
  placeItems: "center",
  padding: 20,
};

const modalCard: CSSProperties = {
  width: 460,
  maxWidth: "100%",
  maxHeight: "calc(100vh - 40px)",
  overflowY: "auto",
  background: "white",
  borderRadius: 22,
  padding: 30,
  boxShadow: "0 24px 70px rgba(0, 0, 0, 0.3)",
};

const modalLabel: CSSProperties = {
  display: "block",
  color: "#6b7280",
  fontWeight: 700,
  marginBottom: 7,
};

const modalTotal: CSSProperties = {
  fontSize: 48,
  margin: "0 0 25px",
};

const tenderInput: CSSProperties = {
  width: "100%",
  padding: 18,
  border: "2px solid #111827",
  borderRadius: 12,
  fontSize: 28,
  fontWeight: 800,
};

const quickAmountGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 9,
  marginTop: 8,
};

const changeBox: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  marginTop: 20,
  padding: 18,
  borderRadius: 12,
  background: "#f3f4f6",
  fontSize: 22,
};

const successMark: CSSProperties = {
  width: 70,
  height: 70,
  display: "grid",
  placeItems: "center",
  margin: "0 auto",
  borderRadius: "50%",
  background: "#dcfce7",
  color: "#15803d",
  fontSize: 38,
  fontWeight: 900,
};

const receiptSummary: CSSProperties = {
  display: "grid",
  gap: 12,
  padding: 18,
  borderRadius: 14,
  background: "#f3f4f6",
};

const messageText: CSSProperties = {
  minHeight: 24,
  marginTop: 14,
  color: "#374151",
  fontWeight: 700,
};

const errorText: CSSProperties = {
  minHeight: 24,
  color: "crimson",
  textAlign: "center",
};

export default App;


const posMenuTrigger: CSSProperties = {
  position: "fixed",
  top: 24,
  left: 24,
  width: 46,
  height: 46,
  border: "none",
  borderRadius: 10,
  background: "#0f172a",
  color: "#ffffff",
  fontSize: 25,
  fontWeight: 700,
  cursor: "pointer",
  zIndex: 1102,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.22)",
};

const posMenuOverlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  border: "none",
  padding: 0,
  background: "rgba(15, 23, 42, 0.54)",
  cursor: "default",
  zIndex: 1100,
};

const posMenuPanel: CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  width: "min(340px, 88vw)",
  height: "100vh",
  padding: "28px 22px",
  boxSizing: "border-box",
  background: "#ffffff",
  zIndex: 1101,
  display: "flex",
  flexDirection: "column",
  boxShadow: "18px 0 50px rgba(15, 23, 42, 0.24)",
  overflowY: "auto",
};

const posMenuHeader: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 3,
  paddingLeft: 58,
  minHeight: 50,
  justifyContent: "center",
  marginBottom: 22,
};

const posMenuBrand: CSSProperties = {
  fontSize: 22,
  color: "#0f172a",
};

const posMenuSubtitle: CSSProperties = {
  fontSize: 13,
  color: "#64748b",
};

const posMenuSession: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 3,
  padding: 14,
  marginBottom: 18,
  borderRadius: 10,
  background: "#f1f5f9",
  color: "#0f172a",
};

const posMenuNavigation: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const posMenuButton: CSSProperties = {
  width: "100%",
  minHeight: 46,
  padding: "11px 14px",
  border: "1px solid #dbe3ec",
  borderRadius: 9,
  background: "#ffffff",
  color: "#172033",
  fontSize: 15,
  fontWeight: 650,
  textAlign: "left",
  cursor: "pointer",
};

const posMenuActiveButton: CSSProperties = {
  background: "#0f172a",
  borderColor: "#0f172a",
  color: "#ffffff",
};

const posMenuBackofficeButton: CSSProperties = {
  marginTop: 8,
  borderColor: "#0f172a",
  color: "#0f172a",
};

const posMenuLogoutButton: CSSProperties = {
  width: "100%",
  minHeight: 48,
  marginTop: "auto",
  padding: "12px 14px",
  border: "1px solid #fecaca",
  borderRadius: 9,
  background: "#fff1f2",
  color: "#b42318",
  fontSize: 15,
  fontWeight: 700,
  cursor: "pointer",
};
