/**
 *  Copyright 2018 SmartBear Software
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

package io.swagger.petstore.model;

import io.swagger.v3.oas.annotations.media.Schema;

import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import java.util.Date;
import java.util.UUID;
import java.math.BigDecimal;

@XmlRootElement(name = "Order")
public class Order {
  private UUID id;
  private UUID petId;
  private Integer quantity;
  private Date shipDate;
  private OrderStatus status;
  private Boolean complete;
  private UUID userId;
  private Date createdAt;
  private BigDecimal unitPrice;
  private BigDecimal totalAmount;
  private String currency;
  private DeliveryDetails deliveryDetails;
  private PaymentStatus paymentStatus;
  private Date paymentExpiresAt;

  @XmlElement(name = "id")
  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

    public Boolean isComplete() {
        return complete;
    }

    public void setComplete(Boolean complete) {
        this.complete = complete;
    }


  @XmlElement(name = "petId")
  public UUID getPetId() {
    return petId;
  }

  public void setPetId(UUID petId) {
    this.petId = petId;
  }

  @XmlElement(name = "quantity")
  public Integer getQuantity() {
    return quantity;
  }

  public void setQuantity(Integer quantity) {
    this.quantity = quantity;
  }

  @XmlElement(name = "status")
  @Schema(description = "Order Status", allowableValues = "placed,approved,shipped,delivered,cancelled")
  public OrderStatus getStatus() {
    return status;
  }

  public void setStatus(OrderStatus status) {
    this.status = status;
  }

  @XmlElement(name = "shipDate")
  public Date getShipDate() {
    return shipDate;
  }

  public void setShipDate(Date shipDate) {
    this.shipDate = shipDate;
  }

  public UUID getUserId() {
    return userId;
  }

  public void setUserId(final UUID userId) {
    this.userId = userId;
  }

  public Date getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(final Date createdAt) {
    this.createdAt = createdAt;
  }

  public BigDecimal getUnitPrice() {
    return unitPrice;
  }

  public void setUnitPrice(final BigDecimal unitPrice) {
    this.unitPrice = unitPrice;
  }

  public BigDecimal getTotalAmount() {
    return totalAmount;
  }

  public void setTotalAmount(final BigDecimal totalAmount) {
    this.totalAmount = totalAmount;
  }

  public String getCurrency() {
    return currency;
  }

  public void setCurrency(final String currency) {
    this.currency = currency;
  }

  public DeliveryDetails getDeliveryDetails() {
    return deliveryDetails;
  }

  public void setDeliveryDetails(final DeliveryDetails deliveryDetails) {
    this.deliveryDetails = deliveryDetails;
  }

  public PaymentStatus getPaymentStatus() {
    return paymentStatus;
  }

  public void setPaymentStatus(final PaymentStatus paymentStatus) {
    this.paymentStatus = paymentStatus;
  }

  public Date getPaymentExpiresAt() {
    return paymentExpiresAt;
  }

  public void setPaymentExpiresAt(final Date paymentExpiresAt) {
    this.paymentExpiresAt = paymentExpiresAt;
  }
}
